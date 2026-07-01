// Socket.IO terminal relay. Each browser socket can host multiple
// terminal tabs; each tab is a separate `docker exec` of an interactive
// bash, identified by an opaque `terminalId` minted by the client.
//
// The Map of `terminalId -> { exec, stream, containerId }` is per-socket
// so two browser tabs on the same server each have their own namespace
// (and tearing one socket down doesn't disturb the others).
//
// Events:
//   terminal:attach    { containerId }                → back-compat single PTY ('primary')
//   terminal:create    { containerId, terminalId }    → mint a new PTY
//   terminal:kill      { terminalId }
//   terminal:input     { terminalId, data } | "string"
//   terminal:resize    { terminalId, cols, rows }
//
// `terminal:data` is emitted back to the client with the terminalId so
// the right xterm instance can render it.

const { WORKDIR } = require('../config');
const containers = require('../state/registry');
const { destroySandbox } = require('./docker');

/**
 * Attach all terminal handlers to the given Socket.IO server.
 * @param {import('socket.io').Server} io
 */
function attachTerminal(io) {
  io.on('connection', (socket) => {
    const terminals = new Map(); // terminalId -> { exec, stream, containerId }

    // Spawn a new bash PTY for the given container, register it under
    // `terminalId`, and pipe its output back to the matching tab on the
    // client. Throws on failure (caller is expected to ack the error).
    const spawnTerminal = async (containerId, terminalId) => {
      const entry = containers.get(containerId);
      if (!entry) throw new Error('Container not found');

      // Defensive: if a terminal with this id already exists (e.g. the
      // client retried after a transient error), tear it down first.
      const old = terminals.get(terminalId);
      if (old) {
        try { old.stream.end(); } catch (_) {}
        terminals.delete(terminalId);
      }

      const exec = await entry.container.exec({
        Cmd: ['/bin/bash', '-i'],
        AttachStdin: true,
        AttachStdout: true,
        AttachStderr: true,
        Tty: true,
        WorkingDir: WORKDIR,
        Env: ['TERM=xterm-256color', 'PS1=\\u@sandbox:\\w\\$ '],
      });
      const stream = await exec.start({ hijack: true, stdin: true, Tty: true });
      terminals.set(terminalId, { exec, stream, containerId });

      stream.on('data', (chunk) =>
        socket.emit('terminal:data', {
          terminalId,
          data: chunk.toString('utf8'),
        }),
      );
      stream.on('end', () => {
        socket.emit('terminal:data', {
          terminalId,
          data: '\r\n[process exited]\r\n',
        });
        terminals.delete(terminalId);
      });
      stream.on('error', (e) => {
        socket.emit('terminal:data', {
          terminalId,
          data: `\r\n[error] ${e.message}\r\n`,
        });
      });
      return terminalId;
    };

    // Backwards-compatible: a client that hasn't been upgraded to the new
    // multi-terminal API can still call `terminal:attach` to get a single
    // implicit terminal. We mint an id and treat it like any other tab.
    socket.on('terminal:attach', async ({ containerId }, ack) => {
      try {
        const terminalId = 'primary';
        await spawnTerminal(containerId, terminalId);
        // Record ownership so the disconnect handler can reap the
        // container if no other socket is still using it.
        containers.trackSocketContainer(socket.id, containerId);
        ack?.({ ok: true, terminalId });
      } catch (e) {
        ack?.({ error: e.message });
      }
    });

    // New explicit create event — the frontend's "+" button calls this
    // and gets back the new terminalId.
    socket.on('terminal:create', async ({ containerId, terminalId }, ack) => {
      try {
        const id = await spawnTerminal(containerId, terminalId);
        containers.trackSocketContainer(socket.id, containerId);
        ack?.({ ok: true, terminalId: id });
      } catch (e) {
        ack?.({ error: e.message });
      }
    });

    // Kill a specific terminal tab. The xterm.js instance on the client
    // gets the `[process exited]` message and tears itself down.
    socket.on('terminal:kill', ({ terminalId }) => {
      const t = terminals.get(terminalId);
      if (!t) return;
      try { t.stream.end(); } catch (_) {}
      terminals.delete(terminalId);
    });

    // Per-tab input. Falls back to the `primary` terminal for clients
    // that still use the old single-pty protocol.
    socket.on('terminal:input', (payload) => {
      if (typeof payload === 'string') {
        const t = terminals.get('primary');
        if (t) t.stream.write(payload);
        return;
      }
      const { terminalId, data } = payload || {};
      if (!terminalId) return;
      const t = terminals.get(terminalId);
      if (t) t.stream.write(data ?? '');
    });

    // Per-tab resize. Same fallback for the old protocol.
    socket.on('terminal:resize', async (payload) => {
      const { terminalId, cols, rows } = payload || {};
      const id = terminalId || 'primary';
      const t = terminals.get(id);
      if (!t) return;
      try {
        await t.exec.resize({ h: rows || 24, w: cols || 80 });
      } catch (_) { /* not all docker versions support resize */ }
    });

    socket.on('disconnect', async () => {
      // Tear down every PTY this socket owned.
      for (const t of terminals.values()) {
        try { t.stream.end(); } catch (_) {}
      }
      terminals.clear();

      // Release the socket's container ownership. Any container that no
      // other socket still uses is now an orphan and gets destroyed —
      // AutoRemove:true on the daemon side does the actual reap.
      const orphans = containers.releaseSocket(socket.id);
      for (const id of orphans) {
        destroySandbox(id).catch((e) =>
          console.error(`[replit] failed to destroy orphan ${id}:`, e.message),
        );
      }
    });
  });
}

module.exports = { attachTerminal };
