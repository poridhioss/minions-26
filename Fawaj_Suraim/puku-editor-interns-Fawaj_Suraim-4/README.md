# Container Job Orchestrator — Build From Scratch

A hands-on tutorial that builds a production-grade Docker job orchestrator step by step.

- a Node.js HTTP + WebSocket server that submits jobs to a queue
- a worker that runs each job inside a hardened ephemeral Docker container
- a static frontend that submits jobs and streams logs
- unit tests + a Docker-Compose-driven end-to-end test
- containerization, structured logging, retries, timeouts, cancellation, API-key auth

- **Phase 1 — Local prototype on the host.** Everything runs with bare Node + Docker.
- **Phase 2 — Hardening for production.** Dockerfile, compose stack, auth, e2e tests, the works.

---

## 0. Prerequisites

![alt text](<images/Untitled Diagram.drawio.png>)

Quick check:

```bash
node --version    # v20.x
docker --version  # Docker version 24.x or newer
docker compose version  # v2.x
```
![alt text](<images/Screenshot from 2026-07-11 01-06-02.png>)

---
# Phase 1 — Build the local prototype (on the host)

Pick a project root, e.g. `~/projects/job-orchestrator`, and `cd` into it.

```
mkdir -p ~/projects/job-orchestrator
cd projects/job-orchestrator/
```

## 1.1 Create the project skeleton

Two top-level folders: `backend/` (Node app) and `frontend/` (plain HTML/JS, served as static files).

```bash
mkdir -p backend/src/{lib,queue,services,middleware,worker} backend/test frontend

ls -R
```
![alt text](<images/Screenshot from 2026-07-11 01-26-32.png>)

---

## 1.2 Initialize Node and install dependencies

```bash
cd backend
npm init -y
npm install bullmq dockerode dotenv express ioredis mkdirp uuid ws
npm install -D nodemon
```

Edit the `scripts` block of the generated `backend/package.json` file inside `~/projects/job-orchestrator/backend` folder:

```json
{
  "name": "backend",
  "version": "1.0.0",
  "description": "Container Job Orchestrator",
  "type": "commonjs",
  "main": "src/server.js",
  "scripts": {
    "start:server": "node src/server.js",
    "start:worker": "node src/worker/jobWorker.js",
    "dev:server": "nodemon src/server.js",
    "dev:worker": "nodemon src/worker/jobWorker.js",
    "test:unit": "node --test test/jobStore.test.js test/logStore.test.js"
  }
}
```
---

## 1.3 Start Redis

```bash
# Using Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Verify it works:

```bash
docker exec -it redis redis-cli ping
# PONG
```
![alt text](<images/Screenshot from 2026-07-11 02-02-06.png>)
---

## 1.4 Write a tiny structured logger

Create `backend/src/lib/logger.js` file and paste the code:

```js
// src/lib/logger.js
// Tiny structured logger: timestamp, level, message, plus arbitrary fields.

function emit(level, msg, fields = {}) {
  const line = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...fields,
  };
  const out = JSON.stringify(line);
  if (level === 'error') process.stderr.write(out + '\n');
  else process.stdout.write(out + '\n');
}

module.exports = {
  info: (msg, fields) => emit('info', msg, fields),
  warn: (msg, fields) => emit('warn', msg, fields),
  error: (msg, fields) => emit('error', msg, fields),
  debug: (msg, fields) => {
    if (process.env.LOG_LEVEL === 'debug') emit('debug', msg, fields);
  },
  // Express-style middleware: assigns a request-id and logs every request
  // with its duration.
  middleware: (req, res, next) => {
    const reqId = req.headers['x-request-id'] || require('uuid').v4();
    req.id = reqId;
    res.setHeader('x-request-id', reqId);
    const start = process.hrtime.bigint();
    res.on('finish', () => {
      const durMs = Number(process.hrtime.bigint() - start) / 1e6;
      emit('info', 'http_request', {
        reqId,
        method: req.method,
        path: req.path,
        status: res.statusCode,
        durationMs: Math.round(durMs),
        jobId: req.params && req.params.id,
      });
    });
    next();
  },
};
```

Sanity-check it:

```bash
cd backend
node -e "const log = require('./src/lib/logger'); log.info('hello', {n: 1});"
```

**Expected output (single JSON object on stdout):**

```json
{"ts":"2026-07-10T20:07:01.673Z","level":"info","msg":"hello","n":1}
```

> Why JSON? It survives field additions, query tools like `jq` understand it, and it's the lowest common denominator for every log sink you'll ever use.

---

## 1.5 Write the BullMQ job queue

create `backend/src/queue/jobQueue.js` file and paste the following code:
- it owns the Redis connection and exports a single shared `Queue` instance that both the API and the worker import.

```js
// src/queue/jobQueue.js
const { Queue } = require('bullmq');
require('dotenv').config();

const connection = {
  host: new URL(process.env.REDIS_URL).hostname,
  port: Number(new URL(process.env.REDIS_URL).port) || 6379,
};

const jobQueue = new Queue('container-jobs', { connection });

module.exports = { jobQueue, connection };
```

to create a `.env` file inside your `backend/` directory run the following command in a terminal:

```bash
cd backend
cat > .env <<'EOF'
PORT=3000
REDIS_URL=redis://127.0.0.1:6379
LOG_LEVEL=info
API_KEY=your-api-key

# Worker tuning:
WORKER_CONCURRENCY=2
JOB_TIMEOUT_MS=300000
EOF
```

(change the `API_KEY=` value as you like)

Verify the queue can be instantiated:

```bash
cd backend
node -e "const { jobQueue } = require('./src/queue/jobQueue'); jobQueue.close().then(() => console.log('queue OK'))"
```

**Expected:**

```
queue OK
```

If you see `ECONNREFUSED 127.0.0.1:6379`, Redis isn't running — go back to step `1.3`.

---

## 1.6 Write the on-disk log store

Each job gets an NDJSON file at `backend/logs/<jobId>.log`. One JSON event per line. The same file is read by the WebSocket handler when a new client connects, **so late subscribers see the full history** before any live events.

Create `backend/src/services/logStore.js` file and paste the following code:

```js
// src/services/logStore.js
const fs = require('fs');
const path = require('path');
const { mkdirp } = require('mkdirp');

const LOG_DIR = path.join(process.cwd(), 'logs');

function pathFor(jobId) {
  return path.join(LOG_DIR, `${jobId}.log`);
}

async function append(jobId, line) {
  await fs.promises.mkdir(LOG_DIR, { recursive: true });
  await fs.promises.appendFile(pathFor(jobId), line, 'utf8');
}

async function read(jobId) {
  const file = pathFor(jobId);
  if (!fs.existsSync(file)) return null;
  return fs.promises.readFile(file, 'utf8');
}

module.exports = { append, read, pathFor };
```

Quick round-trip:

```bash
cd backend
node -e "
  (async () => {
    const ls = require('./src/services/logStore');
    await ls.append('demo', JSON.stringify({type:'start'})+'\n');
    console.log(await ls.read('demo'));
  })();
"
```

**Expected:**

```
{"type":"start"}
```

A file `backend/logs/demo.log` was just created with that one line. We will leave it for now; we'll clean these up with a script later.

---

## 1.7 Write the Express app + server

We split the Express app from the HTTP server. Why?

- `app.js` exports a factory `buildApp()` that **doesn't listen on a port**. Tests can mount it directly on `http.createServer` without flapping ports.
- `server.js` builds the app, wraps it in HTTP and a WebSocket server, and adds graceful shutdown.

Create `backend/src/app.js` file and paste the following code:

```js
// src/app.js
// Builds and returns the Express app. server.js wraps it in HTTP + WS;
// tests can mount it on supertest or http directly.

const express = require('express');
const { jobQueue, connection } = require('./queue/jobQueue');
const logStore = require('./services/logStore');
const log = require('./lib/logger');

function buildApp({ subscribers } = {}) {
  const app = express();
  app.use(express.json());
  app.use(log.middleware);

  const path = require('path');
  const fs = require('fs');
  // Serve the static frontend. Layouts we support, in priority order:
  //   1. STATIC_DIR env var (explicit override)
  //   2. <repo>/frontend           (local dev: src/app.js -> ../../frontend)
  //   3. <repo>/backend/public     (legacy)
  //   4. <WORKDIR>/public          (Docker: WORKDIR=/app, src/app.js -> ../public)
  const candidates = [
    process.env.STATIC_DIR,
    path.join(__dirname, '..', '..', 'frontend'),
    path.join(__dirname, '..', '..', 'public'),
    path.join(__dirname, '..', 'public'),
  ].filter(Boolean);
  const staticDir = candidates.find((p) => fs.existsSync(path.join(p, 'index.html')));
  if (!staticDir) {
    log.warn('static_dir_not_found', { tried: candidates });
  } else {
    log.info('static_dir_serving', { dir: staticDir });
  }
  app.use(express.static(staticDir || candidates[candidates.length - 1]));

  // Serve index.html for the root path so the UI loads at "/".
  app.get('/', (_req, res, next) => {
    if (!staticDir) return next();
    res.sendFile(path.join(staticDir, 'index.html'));
  });

  // 1) Submit a new job
  app.post('/jobs', async (req, res) => {
    const { image, command } = req.body;
    if (!image || !command) {
      return res.status(400).json({ error: 'image and command are required' });
    }
    const jobId = require('uuid').v4();
    await jobQueue.add(
      'run',
      { jobId, image, command },
      {
        jobId,
        attempts: 3,
        backoff: { type: 'exponential', delay: 1000 },
        removeOnComplete: { age: 3600, count: 1000 },
        removeOnFail: { age: 24 * 3600 },
      }
    );
    res.status(202).json({ jobId });
  });

  app.get('/jobs/:id/logs', async (req, res) => {
    const content = await logStore.read(req.params.id);
    if (content === null) return res.status(404).json({ error: 'no_logs' });
    const lines = content.split('\n').filter(Boolean).map((l) => JSON.parse(l));
    res.json({ jobId: req.params.id, lines });
  });

  // Health endpoint (no auth) for orchestrators / load balancers.
  app.get('/healthz', (_req, res) => res.json({ status: 'ok' }));

  return app;
}

module.exports = { buildApp, connection, jobQueue };
```

Create `backend/src/server.js` file and paste the following code:

```js
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
```

Sanity-test the server:

```bash
cd backend
node src/server.js &      # background
sleep 1
curl -s http://localhost:3000/healthz
kill %1
```

**Expected:**

```
{"status":"ok"}
```

And on the server terminal you'll see one log line per request:

```
{"ts":"2025-07-10T17:03:11.123Z","level":"info","msg":"server_started","port":3000}
{"ts":"2025-07-10T17:03:11.987Z","level":"info","msg":"http_request","reqId":"...","method":"GET","path":"/healthz","status":200,"durationMs":2}
```
![alt text](<images/Screenshot from 2026-07-11 04-07-57.png>)

---

## 1.8 Write the worker that runs Docker containers

This is the core of the system. The worker:

1. pulls the requested image
2. creates a hardened container (read-only root, no caps, no network, limited RAM/CPU)
3. demuxes stdout/stderr, line-buffers them, publishes each line to Redis pub/sub **and** writes it to disk
4. waits for the container to exit, with a hard timeout
5. cleans up

Create `backend/src/services/jobStore.js` file and paste the following (we'll extend it in Phase 2 for status + cancel; for now it's empty):

```js
// src/services/jobStore.js
// Phase 1 stub. Phase 2 adds getStatus + cancelJob.
module.exports = {};
```

Create `backend/src/worker/jobWorker.js` file and paste the following:

```js
// src/worker/jobWorker.js
require('dotenv').config();
const { Worker } = require('bullmq');
const Docker = require('dockerode');
const IORedis = require('ioredis');
const { connection } = require('../queue/jobQueue');
const { v4: uuid } = require('uuid');
const logStore = require('../services/logStore');
const log = require('../lib/logger');

const docker = new Docker(); // uses /var/run/docker.sock by default
const pub = new IORedis(connection);

const channelFor = (jobId) => `bull:container-jobs:${jobId}`;

const containersByJobId = new Map();

const worker = new Worker(
  'container-jobs',
  async (job) => {
    const { jobId, image, command } = job.data;
    const channel = channelFor(jobId);

    const publish = (event) => pub.publish(channel, JSON.stringify(event));
    const logLine = (event) =>
      logStore.append(jobId, JSON.stringify(event) + '\n')
        .catch((err) => log.error('logstore_write_failed', { jobId, err: err.message }));

    publish({ type: 'start', jobId, image, command });
    logLine({ type: 'start', jobId, image, command });

    // Pull image (idempotent — no-op if already present)
    publish({ type: 'log', stream: 'system', data: `Pulling ${image}...\n` });
    logLine({ type: 'log', stream: 'system', data: `Pulling ${image}...\n` });
    await new Promise((resolve, reject) => {
      docker.pull(image, (err, stream) => {
        if (err) return reject(err);
        docker.modem.followProgress(stream, (err) => (err ? reject(err) : resolve()));
      });
    });

    // Create + start container
    const containerSpec = {
      Image: image,
      Cmd: ['sh', '-c', command],
      Tty: false,
      HostConfig: {
        Memory: 256 * 1024 * 1024,  // 256 MB hard cap
        NanoCpus: 500_000_000,      // 0.5 vCPU
        PidsLimit: 64,              // 64 processes max
        NetworkMode: 'none',        // fully isolated; flip to 'bridge' if needed
        ReadonlyRootfs: true,       // can't write anywhere except tmpfs mounts
        AutoRemove: true,
        CapDrop: ['ALL'],           // start with zero capabilities
        SecurityOpt: ['no-new-privileges:true'],
        Tmpfs: {
          '/tmp': 'size=64m',
          '/run': 'size=16m',
        },
        Ulimits: [
          { Name: 'nofile', Soft: 1024, Hard: 1024 },
          { Name: 'nproc',  Soft: 64,   Hard: 64   },
        ],
      },
    };
    if (process.env.JOB_USER) containerSpec.User = process.env.JOB_USER;

    const container = await docker.createContainer(containerSpec);
    await container.start();
    containersByJobId.set(jobId, container);

    // Demux stream so stdout and stderr stay separate.
    const makeLineBufferedWriter = (streamName) => {
      let buf = '';
      const flush = (force) => {
        let idx;
        while ((idx = buf.indexOf('\n')) !== -1) {
          const line = buf.slice(0, idx) + '\n';
          buf = buf.slice(idx + 1);
          publish({ type: 'log', stream: streamName, data: line });
          logLine({ type: 'log', stream: streamName, data: line });
        }
        if (force && buf.length) {
          const tail = buf + '\n';
          buf = '';
          publish({ type: 'log', stream: streamName, data: tail });
          logLine({ type: 'log', stream: streamName, data: tail });
        }
      };
      return {
        write: (chunk) => { buf += chunk.toString(); flush(false); },
        end: () => flush(true),
      };
    };

    container.logs({ follow: true, stdout: true, stderr: true }, (err, stream) => {
      if (err) {
        publish({ type: 'error', data: err.message });
        logLine({ type: 'error', data: err.message });
        return;
      }
      const stdoutW = makeLineBufferedWriter('stdout');
      const stderrW = makeLineBufferedWriter('stderr');
      docker.modem.demuxStream(
        stream,
        { write: (chunk) => stdoutW.write(chunk), end: () => stdoutW.end() },
        { write: (chunk) => stderrW.write(chunk), end: () => stderrW.end() }
      );
    });

    // Wait for the container to exit, with a timeout so a runaway job can't pin a worker.
    const timeoutMs = Number(process.env.JOB_TIMEOUT_MS) || 5 * 60 * 1000;
    let timedOut = false;
    const waitPromise = container.wait();
    const timer = setTimeout(async () => {
      timedOut = true;
      try { await container.kill(); } catch (_) {}
      publish({ type: 'log', stream: 'system', data: `[timeout] killed after ${timeoutMs}ms\n` });
      logLine({ type: 'log', stream: 'system', data: `[timeout] killed after ${timeoutMs}ms\n` });
    }, timeoutMs);

    const result = await waitPromise;
    clearTimeout(timer);

    publish({ type: 'exit', jobId, statusCode: result.StatusCode, timedOut });
    logLine({ type: 'exit', jobId, statusCode: result.StatusCode, timedOut });

    if (timedOut) throw new Error(`job_timed_out_after_${timeoutMs}ms`);
    return { statusCode: result.StatusCode };
  },
  { connection, concurrency: Number(process.env.WORKER_CONCURRENCY) || 2 }
);

worker.on('failed', async (job, err) => {
  const jobId = job && job.data ? job.data.jobId : null;
  if (!jobId) return;
  const channel = channelFor(jobId);
  pub.publish(channel, JSON.stringify({ type: 'error', data: err.message }));
  logStore.append(jobId, JSON.stringify({ type: 'error', data: err.message }) + '\n')
        .catch((e) => log.error('logstore_write_failed', { jobId, err: e.message }));
  log.error('job_failed', { jobId, attemptsMade: job.attemptsMade, err: err.message });

  const container = containersByJobId.get(jobId);
  if (container) {
    try { await container.kill(); } catch (_) { }
    try { await container.remove({ force: true }); } catch (_) { }
    containersByJobId.delete(jobId);
  }
});

worker.on('completed', (job, ret) => {
  log.info('job_completed', { jobId: job.data.jobId, returnvalue: ret });
});

log.info('worker_started', { queue: 'container-jobs' });

// Graceful shutdown: stop pulling new jobs, let the in-flight one finish,
// kill any containers still tracked, then disconnect Redis.
let shuttingDown = false;
async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  log.info('worker_shutdown_started', { signal });

  try { await worker.close(); } catch (e) { log.error('worker_close_error', { err: e.message }); }

  for (const [jobId, container] of containersByJobId.entries()) {
    try { await container.kill(); } catch (_) {}
    try { await container.remove({ force: true }); } catch (_) {}
    containersByJobId.delete(jobId);
  }

  try { await pub.quit(); } catch (_) {}
  log.info('worker_shutdown_complete');
  process.exit(0);
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
```

> **Why so much defense in depth?** This code lets users submit arbitrary commands. Every line that says `capDrop ALL`, `ReadonlyRootfs`, `NetworkMode: none`, `PidsLimit`, etc. is a wall between the user command and the host. Lift the network mode only when you specifically need egress and you understand what that means.

---

## 1.9 Write the static frontend

`cd` to the root directory of your project and create `frontend/index.html` file:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Job Orchestrator</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23111'/%3E%3Ctext x='50%25' y='54%25' font-family='monospace' font-size='38' fill='%2300ff88' text-anchor='middle' dominant-baseline='middle'%3E%26gt;_%3C/text%3E%3C/svg%3E" />
  <style>
    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 24px auto; padding: 0 16px; }
    textarea { width: 100%; height: 80px; font-family: monospace; }
    pre { background: #111; color: #eaeaea; padding: 12px; height: 360px; overflow: auto; }
    input { width: 100%; }
    button { padding: 8px 16px; margin-right: 8px; }
    label { display: block; margin: 12px 0; }
  </style>
</head>
<body>
  <h1>Container Job Orchestrator</h1>

  <label>Image
    <input id="image" value="alpine" />
  </label>
  <label>Command
    <textarea id="command">echo hello && sleep 1 && echo world</textarea>
  </label>
  <label>API Key
    <input id="key" type="password" placeholder="optional" />
  </label>
  <button id="submit">Run Job</button>
  <button id="clear" type="button">Clear Log</button>

  <pre id="logs"></pre>

  <script src="/app.js"></script>
</body>
</html>
```

Create `frontend/app.js` file and paste the following code:

```js
const $ = (id) => document.getElementById(id);
const logs = $('logs');

let runCount = 0;

function append(text) {
  logs.textContent += text;
  logs.scrollTop = logs.scrollHeight;
}

function separator(jobId) {
  runCount += 1;
  append(`\n────── run #${runCount}  jobId=${jobId}  ──────\n`);
}

$('clear').onclick = () => {
  logs.textContent = '';
  runCount = 0;
  append('[log cleared]\n');
};

$('submit').onclick = async () => {
  const res = await fetch('/jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...($('key').value ? { 'x-api-key': $('key').value } : {})
    },
    body: JSON.stringify({
      image: $('image').value,
      command: $('command').value,
    })
  });
  const { jobId } = await res.json();
  separator(jobId);

  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}?jobId=${jobId}${ $('key').value ? '&token=' + encodeURIComponent($('key').value) : '' }`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => append(e.data + '\n');
  ws.onclose = () => append('[closed]\n');
};
```

The script is loaded as `/app.js` (the file path) because `express.static(frontendDir)` exposes the entire `frontend/` folder.

---
Right now your project tree should look like:
```
job-orchestrator/
├── .env
├── logs
│   ├── demo.log
├── frontend/
│   ├── index.html
│   └── app.js
└── backend/
    ├── package.json
    ├── .env
    ├── src/
    │   ├── server.js
    │   ├── app.js
    │   ├── lib/logger.js
    │   ├── queue/jobQueue.js
    │   ├── services/
    │   │   ├── jobStore.js
    │   │   └── logStore.js
    │   ├── middleware/
    │   │
    │   └── worker/jobWorker.js
    └── test/
```

## 1.10 Run server + worker and verify a job end-to-end

Open **two terminals**, both `cd backend`.

```bash
# Terminal 1 — API server
npm run dev:server
```

**Expected:**

```
{"ts":"2026-07-10T22:40:51.619Z","level":"info","msg":"server_started","port":3000}
{"ts":"2026-07-10T22:40:51.626Z","level":"info","msg":"static_dir_serving","dir":"/home/fawaj_suraim/projects/job-orchestrator/frontend"}
```

```bash
# Terminal 2 — worker
npm run dev:worker
```

**Expected:**

```
{"ts":"2026-07-10T22:41:08.872Z","level":"info","msg":"worker_started","queue":"container-jobs"}
```

Open `http://localhost:3000` in a browser.

Click **Run Job**.(If you configure a API-KEY inside `.env` file you have to put it on the placeholder, otherwise job will not be executed. If you didn't configure any custom API-KEY put `your-api-key` in the placeholder)

First time pulls `alpine`, ~5 seconds; afterwards the logs stream.
You should see:

![alt text](<images/Screenshot from 2026-07-11 04-49-26.png>)

Click **Run Job** a few more times. Logs accumulate; the `Clear Log` button wipes the pane and resets the run counter.

Verify the same data on disk:

```bash
ls backend/logs/

cat backend/logs/3c1f*.log
```
![alt text](<images/Screenshot from 2026-07-11 05-02-03.png>)

Verify the same via curl, which is what a CI pipeline would do:

```bash
# Submit a job
curl -sS -X POST http://localhost:3000/jobs \
  -H "Content-Type: application/json" \
  -d '{"image":"alpine","command":"echo hi && sleep 1 && echo bye"}'
# → {"jobId":"<uuid>"}

# Stream the persisted logs
curl -sS http://localhost:3000/jobs/<uuid>/logs | python3 -m json.tool
```

**Expected** (3 lines for a simple echo job, formatted for readability):

![alt text](<images/Screenshot from 2026-07-11 05-22-43.png>) ![alt text](<images/Screenshot from 2026-07-11 05-23-04.png>)

> Notice: `POST /jobs` returned `202 Accepted`, not `200 OK`. That's the right HTTP verb for "I accepted your work and will do it later". A real client should poll `GET /jobs/:id` and stream `GET /jobs/:id/logs` while it runs — but for that you need the `/jobs/:id` endpoint, which lands in Phase 2.

---

## 1.11 Write unit tests

Node ships with `node:test`. No extra deps. We have a test stub for BullMQ so unit tests don't need Redis.

Create `backend/test/__bullmq_stub.js` file and paste the following:

```js
class Queue {
  constructor() {}
  async getJob(id) { return id === 'j1' ? global.__stubJob : undefined; }
  async close() {}
}
module.exports = { Queue };
```

Create `backend/test/logStore.test.js` file and paste the following:

```js
// Round-trips logStore against a tmp directory so we never touch the
// real logs/ folder.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const realCwd = process.cwd();
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'logstore-'));
process.chdir(tmp);

const logStore = require('../src/services/logStore');

test('append + read round-trip preserves line ordering', async () => {
  const id = 'abc-123';
  await logStore.append(id, JSON.stringify({ type: 'start' }) + '\n');
  await logStore.append(id, JSON.stringify({ type: 'log', data: 'hello\n' }) + '\n');
  const content = await logStore.read(id);
  assert.ok(content.includes('"type":"start"'));
  assert.ok(content.includes('"data":"hello\\n"'));
  assert.equal(content.split('\n').filter(Boolean).length, 2);
});

test('read returns null for unknown job id', async () => {
  const content = await logStore.read('does-not-exist');
  assert.equal(content, null);
});

test('pathFor returns a path under logs/', () => {
  const p = logStore.pathFor('xyz');
  assert.ok(p.endsWith(path.join('logs', 'xyz.log')));
});

test.after(() => {
  process.chdir(realCwd);
  fs.rmSync(tmp, { recursive: true, force: true });
});
```

Open a terminal and Run the unit tests:

```bash
cd backend
npm run test:unit
```

**Expected:**

![alt text](<images/Screenshot from 2026-07-11 05-36-42.png>)

---

# Phase 2 — Hardening for production

You have a working system on your laptop. Now we harden it: add auth, status/cancel, containerize it, and write the e2e test that runs the entire stack inside Docker Compose.

---

## 2.1 Add API-key auth

Add `backend/src/middleware/auth.js`:

```js
// src/middleware/auth.js
const crypto = require('node:crypto');

// Constant-time comparison so a leaked timing oracle can't be used to
// brute-force the key character by character.
function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

module.exports = function requireApiKey(req, res, next) {
  const expected = process.env.API_KEY;
  // Auth disabled if API_KEY isn't set. Loudly warn — silent-no-auth is a footgun.
  if (!expected) {
    req.log?.warn?.('auth_disabled_no_api_key_env');
    return next();
  }
  if (expected === 'your-api-key') {
    req.log?.warn?.('auth_using_default_key');
  }
  const provided = req.header('x-api-key');
  if (!provided || !safeEqual(provided, expected)) {
    req.log?.warn?.('auth_rejected', { hasProvided: Boolean(provided) });
    return res.status(401).json({ error: 'unauthorized' });
  }
  next();
};
```

Wire it in `backend/src/app.js`. Add the import next to the others:

```js
const requireApiKey = require('./middleware/auth');
```

And inside the `backend/src/app.js` file, add the following line just before `app.post('/jobs', …)` route:

```js
// Apply to all /jobs routes
app.use('/jobs', requireApiKey);
```

Sanity-test:

```bash
# backend/.env temporarily set API_KEY=your-api-key
cd backend
node src/server.js &

# without header → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:3000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"image":"alpine","command":"echo hi"}'
# → 401

# with header → 202
curl -sS -X POST http://localhost:3000/jobs \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: your-api-key' \
  -d '{"image":"alpine","command":"echo hi"}'
# → {"jobId":"<uuid>"}

kill %1
```
![alt text](<images/Screenshot from 2026-07-11 05-59-18.png>)

> **Why `crypto.timingSafeEqual`?** A `===` comparison returns early on the first mismatched byte. That timing difference leaks the key one character at a time over the network. `timingSafeEqual` always touches every byte before returning.

---

## 2.2 Add a Content-Security-Policy middleware

If you ever serve this UI on a public host you'll want the browser to refuse any third-party script it gets tricked into loading. Add `backend/src/middleware/csp.js`:

```js
// src/middleware/csp.js
// Allow inline scripts + eval + inline data-URI images (favicon) + WebSocket
// connections from any origin. Suitable only for a local dev tool.
module.exports = function csp(req, res, next) {
  res.setHeader(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "connect-src 'self' ws: wss:",
    ].join('; ')
  );
  next();
};
```

Wire it in `src/app.js` file:

```js
// put it at the top of the file
const csp = require('./middleware/csp');
```
```js
// add this after initiating the express app
// const app = express() 
app.use(csp);
```

Sanity-test that the header is set:

```bash
curl -sSI http://localhost:3000/ | grep -i content-security-policy
# Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; …
```
![alt text](<images/Screenshot from 2026-07-11 06-19-37.png>)
---

## 2.3 Add job cancellation + status API

Replace `backend/src/services/jobStore.js` with the full version:

```js
// src/services/jobStore.js
const { Queue } = require('bullmq');
const { connection } = require('../queue/jobQueue');

const queue = new Queue('container-jobs', { connection });

async function getStatus(jobId) {
  const job = await queue.getJob(jobId);
  if (!job) return { state: 'unknown' };

  const state = await job.getState(); // 'waiting' | 'active' | 'completed' | 'failed' | 'delayed'
  const exitCode =
    job.returnvalue && typeof job.returnvalue.statusCode === 'number'
      ? job.returnvalue.statusCode
      : null;

  const startedAt = job.processedOn ? new Date(job.processedOn).toISOString() : null;
  const finishedAt = job.finishedOn ? new Date(job.finishedOn).toISOString() : null;
  const queuedAt = job.timestamp ? new Date(job.timestamp).toISOString() : null;
  const durationMs =
    job.processedOn && job.finishedOn ? job.finishedOn - job.processedOn : null;

  return {
    state,
    jobId,
    image: job.data.image,
    command: job.data.command,
    exitCode,
    queuedAt,
    startedAt,
    finishedAt,
    durationMs,
    attemptsMade: job.attemptsMade,
    failedReason: job.failedReason,
  };
}

async function cancelJob(jobId) {
  const job = await queue.getJob(jobId);
  if (!job) return { ok: false, reason: 'not_found' };
  const state = await job.getState();
  if (state === 'completed' || state === 'failed') {
    return { ok: false, reason: 'already_finished' };
  }
  await job.moveToFailed(new Error('cancelled by user'), true);
  return { ok: true };
}

module.exports = { getStatus, cancelJob };
```

Add the routes in `backend/src/app.js`, right after the existing `/jobs` routes:

```js
// import the module
// put it at the top
const { getStatus, cancelJob } = require('./services/jobStore');

// put these routes right after existing /jobs routes
app.get('/jobs/:id', async (req, res) => {
  const status = await getStatus(req.params.id);
  if (status.state === 'unknown') return res.status(404).json({ error: 'not_found' });
  res.json(status);
});

app.post('/jobs/:id/cancel', async (req, res) => {
  const result = await cancelJob(req.params.id);
  if (!result.ok) return res.status(409).json(result);
  res.json(result);
});
```

Sanity-test:

```bash
curl -sS -X POST http://localhost:3000/jobs \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: your-api-key' \
  -d '{"image":"alpine","command":"sleep 120"}'
# → {"jobId":"…"}

curl -sS http://localhost:3000/jobs/… -H 'x-api-key: your-api-key'
# → {"state":"active","exitCode":null,"queuedAt":"…","startedAt":"…","finishedAt":null,"durationMs":null,"attemptsMade":1,…}

# Cancel:
curl -sS -X POST http://localhost:3000/jobs/.../cancel -H 'x-api-key: your-api-key'
# → {"ok":true}
```

---

## 2.4 Add retries, timeout and graceful shutdown

Most of the work is already done — retries and timeouts live in `jobWorker.js` and the BullMQ config is already in `app.js`.

The only thing left is **observability for retries**. Verify by killing or restarting the worker mid-job:

```bash
# submit a long job
curl -sS -X POST http://localhost:3000/jobs -H 'x-api-key: your-api-key' -H 'Content-Type: application/json' \
  -d '{"image":"alpine","command":"sleep 60"}'
```
**then in the worker terminal, type `rs` for restart the worker or `Ctrl+C` for shut it down and then restart the worker using `npm run dev:worker`**

worker restarts → the job is retried with backoff; and BullMQ reschedules

**Expected** in the worker logs after restart (it may take a minute or two to complete the job):

![alt text](<images/Screenshot from 2026-07-12 02-51-12.png>)

(The job ran on a fresh worker after the backoff; `attemptsMade` will be 2 in `GET /jobs/:id`.)

Graceful shutdown was wired in **1.7** and **1.8** (`process.on('SIGTERM', shutdown)`). Verify by sending SIGTERM:

```bash
kill -TERM <pid-of-server>    
kill -TERM <pid-of-worker>    
```
 ![alt text](<images/Screenshot from 2026-07-12 03-13-44.png>)

 Your server and the worker should be terminated.

 ![alt text](<images/Screenshot from 2026-07-12 03-14-27.png>)
---

## 2.5 Containerize with a Dockerfile

A single image is shared between server, worker, and test-runner. The role is chosen by `CMD` at run time.

Create `backend/Dockerfile`:

```dockerfile
# Multi-stage-ish single image used for both the API server and the worker.
# The container runs the role passed via CMD (server or worker).
#
# Build from the REPO ROOT, not from ./backend, so we can COPY ../frontend:
#   docker build -f backend/Dockerfile .
# (docker compose handles this automatically.)

FROM node:20-alpine

# tini gives us proper signal forwarding (SIGTERM) so graceful shutdown runs.
RUN apk add --no-cache tini docker-cli
WORKDIR /app

# Install deps separately so source changes don't bust the layer cache.
COPY backend/package*.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY backend/src ./src
COPY backend/test ./test
COPY frontend ./public

ENV NODE_ENV=production
ENV PORT=3000
ENV REDIS_URL=redis://redis:6379

EXPOSE 3000
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "src/server.js"]
```

> **Why `tini`?** PID 1 in a container is special — it must reap zombie children. By default, `node` doesn't. The `npm install` commands also need `docker-cli` in the image so the worker can talk to the host Docker socket via the bind mount.

Build it:

```bash
cd ..   # repo root 
#~/projects/job-orchestrator/
docker build -f backend/Dockerfile -t job-orchestrator:latest .
```

**Verify** (If the image has build successfully):

```
docker images | grep job-orchestrator
```
![alt text](<images/Screenshot from 2026-07-12 03-27-27.png>)
---

## 2.6 Add Docker Compose

Create `docker-compose.yml` at the repo root (note: **not** inside `backend/`):

```yaml
# Production-ish bring-up. Run from the repo root:
#   docker compose up --build
# The worker service is scaled to 2 replicas; bump with:
#   docker compose up --scale worker=4 -d

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - redis-data:/data

  server:
    # Build context is the REPO ROOT (so ../frontend is reachable).
    # Dockerfile lives at backend/Dockerfile.
    build:
      context: .
      dockerfile: backend/Dockerfile
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    environment:
      PORT: 3000
      REDIS_URL: redis://redis:6379
      # :?  → fail-fast if API_KEY is unset, instead of silently using "your-api-key".
      API_KEY: ${API_KEY:?API_KEY must be set in shell or ./.env}
      LOG_LEVEL: info
      NODE_ENV: production
    ports:
      - "3000:3000"
    volumes:
      - ./backend/logs:/app/logs
    command: ["node", "src/server.js"]

  worker:
    build:
      context: .
      dockerfile: backend/Dockerfile
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
    environment:
      REDIS_URL: redis://redis:6379
      LOG_LEVEL: info
      NODE_ENV: production
      WORKER_CONCURRENCY: "2"
    volumes:
      # Mount the host Docker socket so the worker can create containers.
      # For real production, replace with a Docker socket proxy (tecnativa/docker-socket-proxy).
      - /var/run/docker.sock:/var/run/docker.sock
      - ./backend/logs:/app/logs
    command: ["node", "src/worker/jobWorker.js"]

  # Ephemeral test runner. `npm run test:e2e` does `docker compose run --rm
  # --no-deps test-runner`, which uses the existing redis + worker but spins
  # up a fresh app container for the test process. --no-deps keeps it from
  # restarting the long-running worker on every test run.
  test-runner:
    build:
      context: .
      dockerfile: backend/Dockerfile
    depends_on:
      redis:
        condition: service_healthy
      server:
        condition: service_started
    environment:
      REDIS_URL: redis://redis:6379
      LOG_LEVEL: error
      NODE_ENV: test
      API_KEY: test-key
      WORKER_RUNNING: "1"
    volumes:
      # Share the host's logs dir so the test runner can read what the
      # worker wrote (the worker writes into its own /app/logs mount).
      - ./backend/logs:/app/logs
    command: ["node", "--test", "--test-timeout=120000", "--test-concurrency=1", "test/api.test.js"]


volumes:
  redis-data:
```

`.dockerignore` (also at the repo root) keeps the build context small:

```ignore
# Repo-root .dockerignore — applies to images built from this dir.
# Keep the image context small and avoid baking secrets in.

# VCS / editor / OS junk
.git
.gitignore
.gitattributes
.idea
.vscode
.puku
.DS_Store

# Dependencies (rebuilt inside the image)
**/node_modules

# Local artefacts
**/logs
**/.env
**/.env.local
**/.env.*.local

# Misc
README.md
*.md
```

---

## 2.7 Add the `.env` file + fail-fast API_KEY

Compose auto-loads `.env` from the project root. Create one with a real key:

```bash
cd ..   # repo root
cat > .env <<'EOF'
# Puku Job Orchestrator — root env (auto-loaded by `docker compose`).

API_KEY=your-api-key

# Optional overrides (defaults shown — uncomment to change):
# PORT=3000
# LOG_LEVEL=info
# WORKER_CONCURRENCY=2
# JOB_TIMEOUT_MS=300000
EOF
```

Replace `your-api-key` with a long random string:

```bash
# Generates a 32-char base64 key:
openssl rand -base64 32 | tr -d '\n'; echo
# e.g. oi3KYoWmDUXjrru3ZDrv7kdhQqpsGWVdFgUZCQ0XiMo=
```

Edit `.env` and paste it (excluding the '=' sign at the end of the string):

```dotenv
API_KEY=oi3KYoWmDUXjrru3ZDrv7kdhQqpsGWVdFgUZCQ0XiMo
```

**Carefull** `.env` should be git-ignored. Add to `/.gitignore` at the repo root if it isn't already:

---

## 2.8 Run the stack and submit a job through it

```bash
cd ~/projects/job-orchestrator
docker compose up -d --build
```

**Expected** (excerpt):

![alt text](<images/Screenshot from 2026-07-12 04-19-13.png>) ![alt text](<images/Screenshot from 2026-07-12 04-19-30.png>)

Submit a job with the API key from `.env`:

```bash
KEY=$(grep ^API_KEY .env | sed 's/^API_KEY=//')

curl -sS -X POST http://localhost:3000/jobs \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $KEY" \
  -d '{"image":"alpine","command":"echo compose && sleep 1 && echo works"}'
# → {"jobId":"…"}

curl -sS http://localhost:3000/jobs/<id> -H "x-api-key: $KEY" | python3 -m json.tool
```

**Expected:**

![alt text](<images/Screenshot from 2026-07-12 04-26-14.png>)

Verify a wrong key is rejected:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:3000/jobs \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: wrong' \
  -d '{"image":"alpine","command":"echo hi"}'
# → 401
```
![alt text](<images/Screenshot from 2026-07-12 04-28-17.png>)

Tear down when done:

```bash
docker compose down           # keep volumes
docker compose down -v        # also drop redis data
```

---

## 2.9 Add the e2e test that runs inside Compose

The e2e suite mounts the **real** Express app on a real HTTP server, submits a real job, waits for the worker (running in a sibling container) to complete it, and asserts on the persisted log file. It must run *inside* the compose network so it can talk to `redis:6379`.

`backend/test/api.test.js`:

```js
// End-to-end test: mounts the real Express app on a real HTTP server
// (no listen), submits a job, polls until completion, asserts the new
// result fields, and fetches persisted logs.
//
// REQUIRES: a running Redis AND a running worker process to pick the job up.
// Run with:   npm run test:e2e
// (Skipped automatically if WORKER_RUNNING is not set, so `npm test`
// remains runnable in CI without Docker.)

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

if (process.env.WORKER_RUNNING !== '1') {
  test('API end-to-end (skipped — start a worker and set WORKER_RUNNING=1)', { skip: true }, () => {});
  return;
}

process.env.API_KEY = 'test-key';
process.env.LOG_LEVEL = 'error';

const { buildApp, jobQueue } = require('../src/app');

let server;
let baseUrl;
let jobId;

test.before(async () => {
  const app = buildApp();
  server = http.createServer(app);
  await new Promise((resolve) => server.listen(0, resolve));
  const { port } = server.address();
  baseUrl = `http://127.0.0.1:${port}`;
});

test.after(async () => {
  if (jobId) {
    try { await jobQueue.remove(jobId); } catch (_) {}
  }
  try { await jobQueue.close(); } catch (_) {}
  try { await jobQueue.client.disconnect(); } catch (_) {}
  await new Promise((resolve) => server.close(resolve));
  setImmediate(() => process.exit(0));
});

function fetchJson(path, init = {}) {
  const headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
  if (process.env.API_KEY) headers['x-api-key'] = process.env.API_KEY;
  return fetch(baseUrl + path, { ...init, headers }).then(async (r) => ({
    status: r.status,
    body: r.status === 204 ? null : await r.json(),
  }));
}

test('GET /healthz returns ok', async () => {
  const res = await fetchJson('/healthz');
  assert.equal(res.status, 200);
  assert.deepEqual(res.body, { status: 'ok' });
});

test('POST /jobs rejects missing fields', async () => {
  const res = await fetchJson('/jobs', { method: 'POST', body: JSON.stringify({ image: 'alpine' }) });
  assert.equal(res.status, 400);
  assert.match(res.body.error, /required/);
});

test('POST /jobs with valid input returns 202 + jobId', async () => {
  const res = await fetchJson('/jobs', {
    method: 'POST',
    body: JSON.stringify({ image: 'alpine', command: 'echo test && exit 0' }),
  });
  assert.equal(res.status, 202);
  assert.ok(res.body.jobId);
  jobId = res.body.jobId;
});

test('GET /jobs/:id returns shaped result with exitCode/duration once finished', async () => {
  let state = 'waiting';
  let body;
  // 60s window: cold-cache docker pull + alpine extraction can be slow.
  for (let i = 0; i < 60; i += 1) {
    const res = await fetchJson(`/jobs/${jobId}`);
    body = res.body;
    state = body.state;
    if (state === 'completed' || state === 'failed') break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  assert.equal(state, 'completed', `job did not complete in 60s: ${JSON.stringify(body)}`);
  assert.equal(body.exitCode, 0);
  assert.equal(body.image, 'alpine');
  assert.ok(typeof body.durationMs === 'number' && body.durationMs >= 0);
  assert.ok(body.startedAt && body.finishedAt);
  assert.equal(body.attemptsMade, 1);
});

test('GET /jobs/:id/logs returns persisted NDJSON lines', async () => {
  const res = await fetchJson(`/jobs/${jobId}/logs`);
  assert.equal(res.status, 200);
  assert.equal(res.body.jobId, jobId);
  assert.ok(Array.isArray(res.body.lines));
  const types = res.body.lines.map((l) => l.type);
  assert.ok(types.includes('start'));
  assert.ok(types.includes('exit'));
});

test('GET /jobs/:id returns 404 for unknown id', async () => {
  const res = await fetchJson('/jobs/00000000-0000-0000-0000-000000000000');
  assert.equal(res.status, 404);
});
```

Add a `unit` BullMQ stub test. `backend/test/jobStore.test.js`:

```js
// Unit tests for jobStore — uses an in-memory BullMQ-compatible stub
// so the test suite does not need Redis to run.

const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');

// Stub bullmq before jobStore requires it.
const stubJob = {
  data: { jobId: 'j1', image: 'alpine', command: 'echo hi' },
  timestamp: 1000,
  processedOn: 1100,
  finishedOn: 1200,
  attemptsMade: 1,
  returnvalue: { statusCode: 0 },
  failedReason: undefined,
  getState: async () => 'completed',
  moveToFailed: async () => {},
};
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  if (request === 'bullmq') return require.resolve('./__bullmq_stub.js');
  return originalResolve.call(this, request, ...rest);
};
require('node:fs').writeFileSync(
  require('node:path').join(__dirname, '__bullmq_stub.js'),
  `class Queue {
     constructor() {}
     async getJob(id) { return id === 'j1' ? global.__stubJob : undefined; }
     async close() {}
   }
   module.exports = { Queue };`
);
global.__stubJob = stubJob;

const { getStatus, cancelJob } = require('../src/services/jobStore');

test('getStatus returns shaped result with exit code, timestamps, duration', async () => {
  const status = await getStatus('j1');
  assert.equal(status.state, 'completed');
  assert.equal(status.exitCode, 0);
  assert.equal(status.queuedAt, new Date(1000).toISOString());
  assert.equal(status.startedAt, new Date(1100).toISOString());
  assert.equal(status.finishedAt, new Date(1200).toISOString());
  assert.equal(status.durationMs, 100);
  assert.equal(status.attemptsMade, 1);
  assert.equal(status.image, 'alpine');
  assert.equal(status.command, 'echo hi');
});

test('getStatus returns unknown for missing job', async () => {
  const status = await getStatus('nope');
  assert.deepEqual(status, { state: 'unknown' });
});

test('getStatus returns null exitCode when returnvalue is missing', async () => {
  global.__stubJob.returnvalue = undefined;
  const status = await getStatus('j1');
  assert.equal(status.exitCode, null);
  global.__stubJob.returnvalue = { statusCode: 0 };
});

test('cancelJob rejects already-finished jobs', async () => {
  const result = await cancelJob('j1');
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'already_finished');
});

test('cancelJob returns not_found for unknown ids', async () => {
  const result = await cancelJob('missing');
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'not_found');
});
```

Add a driver that brings the stack up (if needed) and runs `test-runner` ephemerally. `backend/test/runE2E.js`:

```js
#!/usr/bin/env node
// Runs the e2e test suite inside the docker-compose stack so it can
// reach redis:6379 + the running worker. Used by `npm run test:e2e`.

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const repoRoot = path.resolve(__dirname, '..', '..');
const composeFile = path.join(repoRoot, 'docker-compose.yml');

function step(label, cmd, args) {
  console.log(`[test:e2e] ${label}`);
  const res = spawnSync(cmd, args, { stdio: 'inherit', cwd: repoRoot });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

// 1) Bring the long-running stack up if it isn't already.
const ps = spawnSync('docker', ['compose', '-f', composeFile, 'ps', '--quiet'], {
  cwd: repoRoot, encoding: 'utf8',
});
const isUp = (ps.stdout || '').trim().length > 0;
if (!isUp) step('stack not running — bringing it up', 'docker', ['compose', '-f', composeFile, 'up', '-d']);
else step('stack already up', 'docker', ['compose', '-f', composeFile, 'ps']);

// 2) Run the test container once (ephemeral, --no-deps keeps worker+server untouched).
step('running test-runner', 'docker', ['compose', '-f', composeFile, 'run', '--rm', '--no-deps', 'test-runner']);
```

Wire the new scripts into `backend/package.json`:

```json
"scripts": {
  "start:server": "node src/server.js",
  "start:worker": "node src/worker/jobWorker.js",
  "dev:server": "nodemon src/server.js",
  "dev:worker": "nodemon src/worker/jobWorker.js",
  "test": "node --test --test-concurrency=1 test/*.test.js",
  "test:unit": "node --test test/jobStore.test.js test/logStore.test.js",
  "test:e2e": "node ./test/runE2E.js"
}
```

Run the e2e suite. It's the moment of truth (build the docker image first):

```bash
# ~/projects/job-orchestrator
docker compose build
# rebuilds all the images
cd backend
npm run test:e2e
```

**Expected** (≈ 7 seconds end-to-end):

![alt text](<images/Screenshot from 2026-07-12 04-47-09.png>) ![alt text](<images/Screenshot from 2026-07-12 04-47-59.png>)

---

Open a browser and reinspect your UI on `http://localhost:3000`

![alt text](<images/Screenshot from 2026-07-12 04-59-23.png>)

## 2.10 Final tree + commands cheat sheet

After both phases are complete, the project tree is:

```
job-orchestrator/
├── docker-compose.yml           # redis + server + worker + test-runner
├── .env                         # API_KEY=…   (gitignored)
├── .env.example                 # template committed to git
├── .dockerignore
├── frontend/
│   ├── index.html               # static UI (served via express.static)
│   └── app.js                   # submits jobs, streams WebSocket logs
└── backend/
    ├── Dockerfile               # one image, role chosen by `CMD`
    ├── package.json             # scripts: dev:*, test:unit, test:e2e
    ├── .env                     # REDIS_URL, API_KEY, … (for host dev only)
    ├── src/
    │   ├── server.js            # HTTP + WS + graceful shutdown
    │   ├── app.js               # buildApp() — routes only
    │   ├── lib/logger.js        # JSON structured logger + http middleware
    │   ├── queue/jobQueue.js    # shared BullMQ Queue instance
    │   ├── services/
    │   │   ├── jobStore.js      # getStatus, cancelJob
    │   │   └── logStore.js      # NDJSON on disk
    │   ├── middleware/
    │   │   ├── auth.js          # x-api-key with timingSafeEqual
    │   │   └── csp.js           # CSP header
    │   └── worker/jobWorker.js  # pulls image, runs hardened container
    └── test/
        ├── runE2E.js            # `npm run test:e2e` entry point
        ├── api.test.js          # full-stack e2e (needs redis + worker)
        ├── jobStore.test.js     # unit, BullMQ stubbed
        ├── logStore.test.js     # unit, tmp dir
        └── __bullmq_stub.js     # stub for unit tests
```

### Day-to-day commands

```bash
# Local development (host machine, with Redis in Docker)
docker run -d --name puku-redis -p 6379:6379 redis:7-alpine
cd backend
npm run dev:server               # terminal 1
npm run dev:worker               # terminal 2
open http://localhost:3000

# Tests
npm run test:unit                # fast, no Redis, no Docker
npm run test:e2e                 # brings the compose stack up first

# Production stack (everything in containers)
cd ..
docker compose up -d --build
curl http://localhost:3000/healthz

# Iterate on worker after changing src/worker/jobWorker.js:
docker compose up -d --build worker

# Scale workers
docker compose up -d --scale worker=4
```

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ECONNREFUSED 127.0.0.1:6379` | Redis isn't running | `docker run -d -p 6379:6379 redis:7-alpine` |
| `401 unauthorized` | `API_KEY` in `.env` doesn't match header | Re-paste the same key in both places; restart server |
| `API_KEY must be set in shell or ./.env` | `.env` missing or `API_KEY=` is empty | Add a strong value to `.env`, then `docker compose up -d` |
| UI loads but logs never appear | Worker isn't running | `docker compose up -d worker`; check `docker compose logs worker` |
| `no such user` when starting a container | `JOB_USER=1000` set but image lacks UID 1000 | Unset `JOB_USER` or rebuild the image with that user |
| `pull access denied` for a private image | `docker login` not done on host | `docker login` in the host shell; the worker reuses the host socket |
| `Failed to fetch` in browser | Frontend URL changed to https but server is http | Plain http on localhost is fine; switch to https only with TLS termination upstream |

You're done. From here, the obvious next steps are:

- move the worker off the host Docker socket onto a **Docker socket proxy** (`tecnativa/docker-socket-proxy`) so a malicious image can't escape its container;
- add **Prometheus metrics** (`/metrics`) for queue depth, job duration, retry counts;
- replace `journalctl -u …` with a log shipper (Vector, Fluent Bit) ingesting the JSON we already emit.

Pick one; they're all ≈ a day's work each.

