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
const fs = require('node:fs');
const path = require('node:path');

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
const injectedJobId = 'corrupted-job';

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

test('POST /jobs rejects non-string image', async () => {
  const res = await fetchJson('/jobs', {
    method: 'POST',
    body: JSON.stringify({ image: 123, command: 'echo hi' }),
  });
  assert.equal(res.status, 400);
  assert.match(res.body.error, /strings/);
});

test('POST /jobs rejects oversized command', async () => {
  const res = await fetchJson('/jobs', {
    method: 'POST',
    body: JSON.stringify({ image: 'alpine', command: 'x'.repeat(70_000) }),
  });
  assert.equal(res.status, 400);
  assert.match(res.body.error, /max length/);
});

test('POST /jobs rejects image with shell metacharacters or path traversal', async () => {
  for (const bad of ['alpine; rm -rf /', '../etc/passwd', 'alpine:latest ', '-alpine', 'alpine CAP_ADD=SOMETHING']) {
    const res = await fetchJson('/jobs', {
      method: 'POST',
      body: JSON.stringify({ image: bad, command: 'echo hi' }),
    });
    assert.equal(res.status, 400, `should reject ${JSON.stringify(bad)}: got ${res.status} ${JSON.stringify(res.body)}`);
    assert.match(res.body.error, /image must match/);
  }
});

test('POST /jobs accepts standard image refs', async () => {
  for (const ok of ['alpine', 'alpine:3.18', 'myorg/myimage', 'gcr.io/google-project/image:tag']) {
    const res = await fetchJson('/jobs', {
      method: 'POST',
      body: JSON.stringify({ image: ok, command: 'echo hi' }),
    });
    assert.equal(res.status, 202, `should accept ${JSON.stringify(ok)}: got ${res.status} ${JSON.stringify(res.body)}`);
  }
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

test('POST /jobs without API key returns 401', async () => {
  // Strip the auth header set by fetchJson.
  const res = await fetch(baseUrl + '/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: 'alpine', command: 'echo hi' }),
  }).then((r) => ({ status: r.status, body: r.status === 204 ? null : r.json() ? r.json() : null }));
  // Note: fetchJson helper always sets x-api-key. We bypass it to assert 401.
  // The branch above returns the raw status without parsing the body.
  assert.equal(res.status, 401);
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

test('GET /jobs/:id/logs tolerates corrupted NDJSON lines', async () => {
  // Inject a corrupted line into the real on-disk log file and confirm the
  // endpoint still returns 200 with the valid lines (and skips the bad one).
  const logFile = path.join(process.cwd(), 'logs', `${injectedJobId}.log`);
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  fs.writeFileSync(
    logFile,
    JSON.stringify({ type: 'start' }) + '\n' +
      'this line is not json\n' +
      JSON.stringify({ type: 'exit', statusCode: 0 }) + '\n',
    'utf8',
  );
  const res = await fetchJson(`/jobs/${injectedJobId}/logs`);
  assert.equal(res.status, 200);
  assert.equal(res.body.lines.length, 2);
  assert.equal(res.body.lines[0].type, 'start');
  assert.equal(res.body.lines[1].type, 'exit');
  fs.rmSync(logFile, { force: true });
});

test('GET /jobs/:id returns 404 for unknown id', async () => {
  const res = await fetchJson('/jobs/00000000-0000-0000-0000-000000000000');
  assert.equal(res.status, 404);
});

test('GET /jobs/:id/logs rejects path-traversal id with 400', async () => {
  // Without SAFE_ID, ../../tmp/secret.log would resolve via path.join and
  // read / delete arbitrary .log files on disk.
  const res = await fetchJson('/jobs/..%2F..%2Fetc%2Fpasswd/logs');
  assert.equal(res.status, 400);
  assert.equal(res.body.error, 'invalid_id');
});

test('DELETE /jobs/:id rejects path-traversal id with 400', async () => {
  const res = await fetchJson('/jobs/foo%2F..%2Fbar', { method: 'DELETE' });
  assert.equal(res.status, 400);
  assert.equal(res.body.error, 'invalid_id');
});

test('GET /jobs returns a list containing the completed job', async () => {
  const res = await fetchJson('/jobs');
  assert.equal(res.status, 200);
  assert.ok(Array.isArray(res.body.jobs));
  // The jobId should appear somewhere in the first 50 rows.
  assert.ok(res.body.jobs.some((j) => j.jobId === jobId));
});