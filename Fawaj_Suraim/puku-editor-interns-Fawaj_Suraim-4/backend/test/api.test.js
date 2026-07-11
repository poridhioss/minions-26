// test/api.test.js
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
  // Force-close everything so the test process can exit cleanly.
  try { await jobQueue.close(); } catch (_) {}
  try { await jobQueue.client.disconnect(); } catch (_) {}
  await new Promise((resolve) => server.close(resolve));
  // Belt-and-braces: tell the test runner we're done. Without this,
  // BullMQ/ioredis keepalive timers can hold the event loop open after
  // all assertions pass and the run looks "interrupted".
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
