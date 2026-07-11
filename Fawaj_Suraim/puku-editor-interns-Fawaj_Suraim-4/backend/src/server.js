// src/server.js
// HTTP + WebSocket server. The Express app is built in ./app.js so tests
// can mount it without binding a port or starting a WS server.

require('dotenv').config();
const http = require('http');
const { WebSocketServer } = require('ws');
const IORedis = require('ioredis');
const { buildApp, connection, jobQueue } = require('./app');
const log = require('./lib/logger');
const logStore = require('./services/logStore');

const app = buildApp();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

// jobId -> Set of WebSocket clients watching that job
const subscribers = new Map();
const sub = new IORedis(connection);

sub.on('message', (channelName, message) => {
  const prefix = 'bull:container-jobs:';
  if (!channelName.startsWith(prefix)) return;
  const jobId = channelName.slice(prefix.length);
  const set = subscribers.get(jobId);
  if (!set) return;
  for (const ws of set) {
    if (ws.readyState === ws.OPEN) ws.send(message);
  }
});

wss.on('connection', async (ws, req) => {
  const url = new URL(req.url, 'http://localhost');
  const token = url.searchParams.get('token');
  if (process.env.API_KEY && token !== process.env.API_KEY) {
    ws.close(1008, 'unauthorized');
    return;
  }
  const jobId = url.searchParams.get('jobId');
  if (!jobId) {
    ws.close(1008, 'jobId required');
    return;
  }

  const channel = `bull:container-jobs:${jobId}`;

  // Replay persisted log first so the client catches up on events that
  // fired before the WebSocket existed.
  try {
    const history = await logStore.read(jobId);
    if (history) {
      for (const line of history.split('\n').filter(Boolean)) {
        if (ws.readyState === ws.OPEN) ws.send(line);
      }
    }
  } catch (err) {
    log.error('replay_failed', { jobId, err: err.message });
  }

  if (!subscribers.has(jobId)) subscribers.set(jobId, new Set());
  subscribers.get(jobId).add(ws);

  try {
    await sub.subscribe(channel);
  } catch (err) {
    subscribers.get(jobId).delete(ws);
    if (subscribers.get(jobId).size === 0) subscribers.delete(jobId);
    ws.close(1011, 'subscribe_failed');
    return;
  }

  ws.send(JSON.stringify({ type: 'connected', jobId }));

  ws.on('close', () => {
    const set = subscribers.get(jobId);
    if (!set) return;
    set.delete(ws);
    if (set.size === 0) {
      subscribers.delete(jobId);
      sub.unsubscribe(channel).catch(() => {});
    }
  });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  log.info('server_started', { port: Number(PORT) });
});

async function shutdown(signal) {
  log.info('shutdown_started', { signal });
  for (const set of subscribers.values()) {
    for (const ws of set) {
      try { ws.close(1001, 'server_shutdown'); } catch (_) {}
    }
  }
  subscribers.clear();
  server.close((err) => {
    if (err) log.error('server_close_error', { err: err.message });
    Promise.allSettled([
      sub.quit().catch(() => {}),
      jobQueue.close().catch(() => {}),
    ]).then(() => {
      log.info('shutdown_complete');
      process.exit(0);
    });
  });
  setTimeout(() => {
    log.error('shutdown_timeout_forcing_exit');
    process.exit(1);
  }, 10_000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('uncaughtException', (err) => {
  log.error('uncaught_exception', { err: err.message, stack: err.stack });
  shutdown('uncaughtException');
});
process.on('unhandledRejection', (reason) => {
  log.error('unhandled_rejection', { reason: String(reason) });
});
