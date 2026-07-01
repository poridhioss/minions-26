// Boot file. Wiring lives here; everything else is in `config/`,
// `state/`, `services/`, and `routes/`. Keep this file boring.

const http = require('http');
const express = require('express');
const cors = require('cors');
const { Server: SocketIOServer } = require('socket.io');

const { PORT, SANDBOX_IMAGE, FALLBACK_IMAGE } = require('./config');
const containers = require('./state/registry');
const { destroySandbox } = require('./services/docker');
const { attachTerminal } = require('./services/terminal');
const health = require('./routes/health');
const containersRoute = require('./routes/containers');
const filesRoute = require('./routes/files');

/* ------------------------------- HTTP layer ------------------------------- */

const app = express();
app.use(cors());
// 5MB cap — Monaco occasionally sends reasonably large file edits and
// we don't want to truncate them, but we also don't want a stray
// `fs.readFile` of a 2GB log to OOM the process.
app.use(express.json({ limit: '5mb' }));

app.use('/', health);
app.use('/', containersRoute);
app.use('/', filesRoute);

/* ------------------------------ Socket.IO ------------------------------ */

const server = http.createServer(app);
const io = new SocketIOServer(server, { cors: { origin: '*' } });
attachTerminal(io);

/* --------------------------------- Boot --------------------------------- */

server.listen(PORT, () => {
  console.log(`[replit] backend listening on http://localhost:${PORT}`);
  console.log(`[replit] sandbox image: ${SANDBOX_IMAGE} (fallback: ${FALLBACK_IMAGE})`);
});

// Best-effort cleanup on Ctrl+C so a stray `node src/server.js` in a
// dev terminal doesn't leave containers running on the host.
process.on('SIGINT', async () => {
  console.log('\n[replit] shutting down, removing containers...');
  for (const id of Array.from(containers.keys())) {
    await destroySandbox(id).catch(() => {});
  }
  process.exit(0);
});

// Tear down on SIGTERM too — Docker `stop` (vs `kill`) gives us ~10s
// to clean up so containers don't linger after `docker compose down`.
process.on('SIGTERM', async () => {
  console.log('[replit] SIGTERM received, removing containers...');
  for (const id of Array.from(containers.keys())) {
    await destroySandbox(id).catch(() => {});
  }
  process.exit(0);
});
