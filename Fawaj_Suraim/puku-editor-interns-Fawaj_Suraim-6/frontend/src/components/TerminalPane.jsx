import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { io } from 'socket.io-client';
import '@xterm/xterm/css/xterm.css';

// One module-level socket, so we never tear it down on re-render.
let _socket = null;
function getSocket() {
  if (!_socket) {
    _socket = io({ transports: ['websocket', 'polling'], autoConnect: true, reconnection: true });
  }
  return _socket;
}

// Mints a short, URL-safe id for a new terminal tab.
function newId() {
  return 't-' + Math.random().toString(36).slice(2, 10);
}

/**
 * Multi-terminal host. Each tab is its own xterm.js instance backed by a
 * separate `docker exec` bash. The header bar exposes tab switching and
 * the `+` / `✕` buttons requested by the user.
 *
 * Imperative API exposed via `apiRef`:
 *   - create()        : spawn a new terminal in the current container
 *   - kill(id?)       : kill the active tab (or the given id)
 *   - write(data)     : forward data to the active tab's xterm
 *   - focus()         : focus the active tab's xterm
 */
const TerminalPane = forwardRef(function TerminalPane({ containerId }, ref) {
  // List of tabs: { id, title, status: 'starting'|'running'|'exited' }
  const [tabs, setTabs] = useState([]);
  const [activeId, setActiveId] = useState(null);

  // Refs that survive re-renders. One slot per tab id, lazily populated.
  const xtermRefs = useRef(new Map()); // id -> Terminal
  const fitRefs = useRef(new Map());   // id -> FitAddon
  const hostRefs = useRef(new Map());  // id -> HTMLDivElement (rendered)
  const statusRefs = useRef(new Map());// id -> 'starting' | 'running' | 'exited'
  const pendingInputs = useRef(new Map()); // id -> string, command to send once the PTY is up
  // `busy` is true while a foreground program is running (between the moment
  // we sent a command and the moment the shell prints a fresh prompt).
  // `tail` keeps the most recent output per tab so we can detect that
  // prompt and flip busy back to false.
  const busyRefs = useRef(new Map());  // id -> bool
  const tailRefs = useRef(new Map());  // id -> string (last ~150 chars of output)

  /* ------------------- busy/tail helpers for free-tab lookup ----------------- */
  // Append a chunk to a tab's running tail (capped so we don't grow without
  // bound) and return the new tail. Used by onData to scan for a fresh
  // shell prompt and flip busy off.
  const appendTail = (id, chunk) => {
    const prev = tailRefs.current.get(id) || '';
    const next = (prev + chunk).slice(-150);
    tailRefs.current.set(id, next);
    return next;
  };
  // Mark a tab as currently running a foreground program.
  const markBusy = (id) => {
    if (!busyRefs.current.get(id)) {
      busyRefs.current.set(id, true);
      setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, busy: true } : t)));
    }
  };
  // Mark a tab as idle (shell is at a prompt). No-op if already idle.
  const markIdle = (id) => {
    if (busyRefs.current.get(id)) {
      busyRefs.current.set(id, false);
      setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, busy: false } : t)));
    }
  };

  /* --------------------- imperative handle for App.jsx --------------------- */
  useImperativeHandle(ref, () => ({
    // True iff there's at least one live tab in the panel. Useful for UI
    // affordances that want to disable themselves when no shell is open.
    hasActive: () => tabs.length > 0,
    create: ({ prefill, title } = {}) => {
      if (!containerId) return null;
      const id = newId();
      setTabs((prev) => [
        ...prev,
        { id, title: title || 'bash ' + (prev.length + 1), status: 'starting', busy: false },
      ]);
      setActiveId(id);
      // If the caller supplied a prefill, stash it so the per-tab effect
      // can pipe it into the PTY once the backend acks terminal:create.
      if (prefill) pendingInputs.current.set(id, prefill);
      return id;
    },
    // Run `command` in the most appropriate existing tab. Returns the id
    // of the tab that received the command, or null if no tab has a live
    // PTY yet (in which case the caller should fall back to `create`).
    //
    // Pick order:
    //   1. The active tab if it's `running` and idle (shell at a prompt).
    //   2. Any other tab that is `running` and idle.
    //   3. The active tab even if it's busy — the user is already looking
    //      at it, bash will queue the command, and the next prompt will
    //      run it.
    //   4. Otherwise null (no PTYs up).
    //
    // Picking an idle tab is the whole point: it stops the editor's Run
    // button from opening a fresh "run:" tab on every click, while still
    // leaving long-running programs to finish in their own tab.
    runInReusableTab: (command) => {
      if (!containerId) return null;
      const isLive = (t) => t.status === 'running';
      const isIdle = (t) => !t.busy;
      const liveTabs = tabs.filter(isLive);
      if (!liveTabs.length) return null;

      const active = liveTabs.find((t) => t.id === activeId);
      const idleActive = active && isIdle(active) ? active : null;
      const idleOther = liveTabs.find((t) => isIdle(t) && t.id !== activeId);
      const target = idleActive || idleOther || active;
      if (!target) return null;

      // Make the target active (and focus its xterm) so the user sees
      // the run output stream in. setActiveId triggers the existing
      // fit+focus effect.
      if (target.id !== activeId) setActiveId(target.id);

      // Pipe the command into the PTY. The shell executes it, output
      // streams back via terminal:data, and the prompt returns cleanly
      // when the program exits.
      const data = command.endsWith('\r') ? command : command + '\r';
      getSocket().emit('terminal:input', { terminalId: target.id, data });
      markBusy(target.id);
      return target.id;
    },
    kill: (id) => {
      const target = id || activeId;
      if (!target) return;
      getSocket().emit('terminal:kill', { terminalId: target });
      // Server will emit terminal:data [process exited] and the cleanup
      // effect below will remove the tab. As a fallback, force-remove it
      // after a short delay in case the server is slow to respond.
      setTimeout(() => {
        setTabs((prev) => prev.filter((t) => t.id !== target));
        if (target === activeId) {
          setActiveId((curr) => {
            const remaining = tabs.filter((t) => t.id !== target);
            return remaining.length ? remaining[remaining.length - 1].id : null;
          });
        }
        const term = xtermRefs.current.get(target);
        if (term) { try { term.dispose(); } catch (_) {} }
        xtermRefs.current.delete(target);
        fitRefs.current.delete(target);
        hostRefs.current.delete(target);
        statusRefs.current.delete(target);
        busyRefs.current.delete(target);
        tailRefs.current.delete(target);
      }, 200);
    },
    write: (data) => {
      const id = activeId;
      if (!id) return;
      const term = xtermRefs.current.get(id);
      if (term) term.write(data);
    },
    focus: () => {
      const id = activeId;
      if (!id) return;
      const term = xtermRefs.current.get(id);
      if (term) term.focus();
    },
  }), [containerId, activeId, tabs]);

  /* ----------------------- spawn a shell when a new tab appears ----------------------- */
  useEffect(() => {
    if (!containerId) return;
    // For each tab in 'starting' state whose host div is now mounted, spin
    // up an xterm + attach it to a backend PTY. We rely on a microtask
    // after setTabs to let React paint the host div.
    const pending = tabs.filter((t) => t.status === 'starting' && hostRefs.current.has(t.id));
    if (!pending.length) return;

    for (const tab of pending) {
      const hostEl = hostRefs.current.get(tab.id);
      if (!hostEl) continue;
      // If we somehow already have an xterm for this id, skip.
      if (xtermRefs.current.has(tab.id)) continue;

      const term = new Terminal({
        cursorBlink: true,
        fontFamily: 'Menlo, Monaco, "Cascadia Mono", "Roboto Mono", monospace',
        fontSize: 13,
        theme: { background: '#0b1020', foreground: '#e6edf3' },
        convertEol: true,
        allowProposedApi: true,
        scrollback: 5000,
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(hostEl);
      requestAnimationFrame(() => { try { fit.fit(); } catch (_) {} });

      xtermRefs.current.set(tab.id, term);
      fitRefs.current.set(tab.id, fit);
      statusRefs.current.set(tab.id, 'starting');

      term.writeln('\x1b[36m[replit-mini]\x1b[0m starting shell…');
      term.focus();

      term.onData((data) => {
        getSocket().emit('terminal:input', { terminalId: tab.id, data });
      });

      const resizeObs = new ResizeObserver(() => {
        try { fit.fit(); } catch (_) {}
        getSocket().emit('terminal:resize', {
          terminalId: tab.id,
          cols: term.cols,
          rows: term.rows,
        });
      });
      resizeObs.observe(hostEl);
      // Stash the observer so cleanup can disconnect it.
      term._resizeObs = resizeObs;

      // Ask the backend to spawn a bash PTY for this tab.
      getSocket().emit(
        'terminal:create',
        { containerId, terminalId: tab.id },
        (ack) => {
          if (ack?.error) {
            term.writeln(`\x1b[31m[replit-mini]\x1b[0m ${ack.error}`);
            statusRefs.current.set(tab.id, 'exited');
            setTabs((prev) => prev.map((t) => (t.id === tab.id ? { ...t, status: 'exited' } : t)));
            return;
          }
          statusRefs.current.set(tab.id, 'running');
          setTabs((prev) => prev.map((t) => (t.id === tab.id ? { ...t, status: 'running' } : t)));
          try { fit.fit(); } catch (_) {}
          getSocket().emit('terminal:resize', {
            terminalId: tab.id,
            cols: term.cols,
            rows: term.rows,
          });
          // If the caller (e.g. the editor's Run button) pre-loaded a
          // command for this tab, pipe it into the PTY now. Trailing \r
          // makes the shell execute it; the program's output will stream
          // back through terminal:data and the prompt will return cleanly
          // when the command finishes — same UX as typing it manually.
          const prefill = pendingInputs.current.get(tab.id);
          if (prefill) {
            pendingInputs.current.delete(tab.id);
            getSocket().emit('terminal:input', {
              terminalId: tab.id,
              data: prefill.endsWith('\r') ? prefill : prefill + '\r',
            });
            markBusy(tab.id);
          }
        },
      );
    }
  }, [tabs, containerId]);

  /* ----------------------- route terminal:data to the right xterm ----------------------- */
  useEffect(() => {
    const s = getSocket();
    const onData = ({ terminalId, data }) => {
      const term = xtermRefs.current.get(terminalId);
      if (term) term.write(data);
      // Track a short rolling tail of each PTY's output so we can tell
      // when the shell has returned to a prompt after a foreground job
      // (used by runInReusableTab to pick a free terminal).
      if (typeof data === 'string' && data.length) {
        const tail = appendTail(terminalId, data);
        // PS1 ends with "$ " (user) or "# " (root) followed by the cursor.
        if (tail.endsWith('$ ') || tail.endsWith('# ')) {
          markIdle(terminalId);
        }
      }
      // Server signals a process exit with [process exited]; mark the tab
      // and remove it after a short pause so the user can see the message.
      if (typeof data === 'string' && data.includes('[process exited]')) {
        statusRefs.current.set(terminalId, 'exited');
        setTabs((prev) => prev.map((t) => (t.id === terminalId ? { ...t, status: 'exited' } : t)));
      }
    };
    s.on('terminal:data', onData);
    return () => { s.off('terminal:data', onData); };
  }, []);

  /* ----------------------- fit + focus the active tab when it changes ----------------------- */
  useEffect(() => {
    if (!activeId) return;
    const fit = fitRefs.current.get(activeId);
    const term = xtermRefs.current.get(activeId);
    if (fit) { try { fit.fit(); } catch (_) {} }
    if (term) { try { term.focus(); } catch (_) {} }
  }, [activeId]);

  /* ----------------------- container change: tear down all tabs ----------------------- */
  useEffect(() => {
    return () => {
      // On unmount or containerId change, dispose every xterm and tell
      // the backend to kill each one. The backend also cleans up on
      // socket disconnect, but being explicit avoids stray processes.
      for (const [id, term] of xtermRefs.current) {
        try { term._resizeObs?.disconnect(); } catch (_) {}
        try { term.dispose(); } catch (_) {}
        getSocket().emit('terminal:kill', { terminalId: id });
      }
      xtermRefs.current.clear();
      fitRefs.current.clear();
      hostRefs.current.clear();
      statusRefs.current.clear();
    };
  }, [containerId]);

  /* ---------------------------------- render ---------------------------------- */
  const activeTab = tabs.find((t) => t.id === activeId);

  return (
    <div className="terminal-host-wrap">
      <div className="terminal-header">
        <div className="terminal-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={'terminal-tab' + (t.id === activeId ? ' active' : '') + (t.status === 'exited' ? ' exited' : '')}
              onClick={() => setActiveId(t.id)}
              title={t.title + (t.status === 'exited' ? ' (exited)' : '')}
            >
              <span className="terminal-tab-dot" data-status={t.status} />
              <span className="terminal-tab-title">{t.title}</span>
            </button>
          ))}
        </div>
        <div className="terminal-actions">
          <button
            className="terminal-add-btn"
            onClick={() => {
              if (!containerId) return;
              const id = newId();
              setTabs((prev) => [...prev, { id, title: `bash ${prev.length + 1}`, status: 'starting' }]);
              setActiveId(id);
            }}
            disabled={!containerId}
            title="New terminal"
          >
            +
          </button>
          <button
            className="terminal-kill-btn"
            onClick={() => {
              const target = activeId;
              if (!target) return;
              getSocket().emit('terminal:kill', { terminalId: target });
              setTimeout(() => {
                setTabs((prev) => prev.filter((t) => t.id !== target));
                setActiveId((curr) => (curr === target
                  ? (tabs.filter((t) => t.id !== target)[0]?.id ?? null)
                  : curr));
                const term = xtermRefs.current.get(target);
                if (term) { try { term.dispose(); } catch (_) {} }
                xtermRefs.current.delete(target);
                fitRefs.current.delete(target);
                hostRefs.current.delete(target);
                statusRefs.current.delete(target);
                busyRefs.current.delete(target);
                tailRefs.current.delete(target);
              }, 200);
            }}
            disabled={!activeTab}
            title="Kill active terminal"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="terminal-bodies">
        {tabs.length === 0 && (
          <div className="terminal-empty">
            {containerId
              ? 'No terminals. Click "+" to spawn one.'
              : 'No sandbox attached. Click "New sandbox" to start one.'}
          </div>
        )}
        {tabs.map((t) => (
          <div
            key={t.id}
            className={'terminal-body' + (t.id === activeId ? ' active' : '')}
            ref={(el) => {
              if (el) hostRefs.current.set(t.id, el);
              else hostRefs.current.delete(t.id);
            }}
          />
        ))}
      </div>
    </div>
  );
});

export default TerminalPane;
