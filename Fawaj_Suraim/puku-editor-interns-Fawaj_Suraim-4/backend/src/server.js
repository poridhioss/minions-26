// src/server.js
// HTTP + WebSocket server. The Express app is built in ./app.js so tests
// can mount it without binding a port or starting a WS server.

require('dotenv').config();
const http = require('http');
const { WebSocketServer } = require('ws');
const IORedis = require('ioredis');
const { buildApp, connection, jobQueue } = require('./app');
const log = require('./lib/logger');
const safeEqual = require('./lib/safeEqual');
const logStore = require('./services/logStore');

const app = buildApp();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

// jobId -> Set of WebSocket clients watching that job
const subscribers = new Map();

// WebSocket auth header (the 'token=' query param) only proves possession of
// the API key, not the page that opened the connection. Pair that check with
// an Origin allowlist so an attacker hosting their own page can't subscribe
// to a job they only have the ID for. By default any origin is allowed —
// suitable for local dev where the frontend and API live on different
// ports/locations. Set ALLOWED_WS_ORIGINS to a comma-separated allowlist
// (e.g. "http://localhost:5173,http://app.example.com") to lock down.
const ALLOWED_WS_ORIGINS = (process.env.ALLOWED_WS_ORIGINS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);

function originAllowed(req) {
  if (ALLOWED_WS_ORIGINS.length === 0) return true;
  const origin = req.headers.origin;
  return origin && ALLOWED_WS_ORIGINS.includes(origin);
}

const sub = new IORedis(connection);
// Without an 'error' handler, an ioredis EventEmitter throws on the next tick
// when Redis disconnects, taking the whole API process down with it.
// Log + keep running; ioredis auto-reconnects and re-issues pending subscribes.
sub.on('error', (err) => log.error('redis_subscriber_error', { err: err.message }));

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
  if (!originAllowed(req)) {
    ws.close(1008, 'origin_not_allowed');
    return;
  }
  const url = new URL(req.url, 'http://localhost');
  const token = url.searchParams.get('token');
  if (process.env.API_KEY && !safeEqual(token || '', process.env.API_KEY)) {
    ws.close(1008, 'unauthorized');
    return;
  }
  const jobId = url.searchParams.get('jobId');
  if (!jobId || !logStore.SAFE_ID.test(jobId)) {
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
