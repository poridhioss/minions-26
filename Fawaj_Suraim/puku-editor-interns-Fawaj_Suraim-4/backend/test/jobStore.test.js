// test/jobStore.test.js
// Unit tests for jobStore — uses an in-memory BullMQ-compatible stub
// so the test suite does not need Redis to run.

const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');

// Stub bullmq before jobStore requires it.
// The stub exposes a mutable `global.__stubJob` so individual tests can
// flip `remove` / `moveToFailed` behaviour to simulate the "worker owns
// the lock" race we hit on delete-mid-job in production.
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
  remove: async () => {},
};
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  if (request === 'bullmq') return require.resolve('./__bullmq_stub.js');
  if (request === 'ioredis') return require.resolve('./__ioredis_stub.js');
  return originalResolve.call(this, request, ...rest);
};
require('node:fs').writeFileSync(
  require('node:path').join(__dirname, '__bullmq_stub.js'),
  `class Queue {
     constructor() {}
     async getJob(id) { return global.__stubJobById?.[id] ?? (id === 'j1' ? global.__stubJob : undefined); }
     async close() {}
   }
   module.exports = { Queue };`
);
require('node:fs').writeFileSync(
  require('node:path').join(__dirname, '__ioredis_stub.js'),
  `class Redis {
     constructor() {
       global.__stubRedisData = global.__stubRedisData || {};
     }
     async get(_k) { return global.__stubRedisData[_k] ?? null; }
     async set(_k, _v, _mode, _ttl) { global.__stubRedisData[_k] = _v; return 'OK'; }
     async del(_k) { delete global.__stubRedisData[_k]; return 0; }
     on() { return this; }
     async quit() { return 'OK'; }
     disconnect() {}
   }
   module.exports = Redis;
   module.exports.default = Redis;`
);
global.__stubJob = stubJob;
global.__stubJobById = undefined;
global.__stubRedisData = {};

const { getStatus, cancelJob, deleteJob } = require('../src/services/jobStore');

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

// getStatus surfaces a user-cancelled job as state='cancelled' regardless
// of how the underlying BullMQ record looks. Two flavours cover both
// worker versions:
//   1. New worker: throws after re-checking the cancel key, so the job
//      ends up `failed` with failedReason="cancelled by user".
//   2. Old worker (or any path where the kill beat the throw): the job
//      ends up `completed` with returnvalue.statusCode=137 (SIGKILL).
// Both shapes MUST be surfaced as `cancelled` so the UI can show the
// right pill instead of "completed exit 137".
test('getStatus returns cancelled for failed jobs with cancelled-by-user reason', async () => {
  const prev = {
    returnvalue: global.__stubJob.returnvalue,
    failedReason: global.__stubJob.failedReason,
    getState: global.__stubJob.getState,
  };
  global.__stubJob.failedReason = 'cancelled by user';
  global.__stubJob.getState = async () => 'failed';
  try {
    const status = await getStatus('j1');
    assert.equal(status.state, 'cancelled');
  } finally {
    global.__stubJob.returnvalue = prev.returnvalue;
    global.__stubJob.failedReason = prev.failedReason;
    global.__stubJob.getState = prev.getState;
  }
});

test('getStatus returns cancelled for completed jobs with exit code 137', async () => {
  const prev = {
    returnvalue: global.__stubJob.returnvalue,
    failedReason: global.__stubJob.failedReason,
    getState: global.__stubJob.getState,
  };
  global.__stubJob.returnvalue = { statusCode: 137 };
  global.__stubJob.failedReason = undefined;
  global.__stubJob.getState = async () => 'completed';
  try {
    const status = await getStatus('j1');
    assert.equal(status.state, 'cancelled');
    // exitCode should still surface — UI may want to show "killed (137)".
    assert.equal(status.exitCode, 137);
  } finally {
    global.__stubJob.returnvalue = prev.returnvalue;
    global.__stubJob.failedReason = prev.failedReason;
    global.__stubJob.getState = prev.getState;
  }
});

test('getStatus returns deleted when the delete key is set', async () => {
  global.__stubRedisData['job-delete:j1'] = '1';
  try {
    const status = await getStatus('j1');
    assert.equal(status.state, 'deleted');
    assert.equal(status.jobId, 'j1');
  } finally {
    delete global.__stubRedisData['job-delete:j1'];
  }
});

// Cancel is idempotent: if the job is already in a terminal BullMQ state
// (or has been TTL'd out of the queue entirely), the user's intent — stop
// the job — is already satisfied. Returning `ok: true` lets the UI drop
// the "Cancelling…" spinner instead of getting stuck.
test('cancelJob is a no-op success for already-finished jobs', async () => {
  const result = await cancelJob('j1');
  assert.equal(result.ok, true);
  assert.equal(result.reason, 'already_finished');
});

test('cancelJob is a no-op success for jobs that have been TTL\'d away', async () => {
  const result = await cancelJob('missing');
  assert.equal(result.ok, true);
  assert.equal(result.reason, 'already_gone');
});

// Delete is also idempotent in the success direction. The first three
// cases below describe the failure modes we saw in production: deleting
// a job mid-flight used to return 404 on the first click because the
// BullMQ remove/moveToFailed path threw while the worker held the lock.
// The container was killed by forceStopContainer in either case, so the
// user's intent was satisfied — we just shouldn't pretend it wasn't.
test('deleteJob is a no-op success for jobs that have been TTL\'d away', async () => {
  const result = await deleteJob('missing');
  assert.equal(result.ok, true);
  assert.equal(result.reason, 'already_gone');
});

test('deleteJob returns ok when BullMQ remove succeeds', async () => {
  global.__stubJobById = undefined; // restore default lookup
  global.__stubJob.remove = async () => {};
  const result = await deleteJob('j1');
  assert.equal(result.ok, true);
  // Either `ok` (no reason) or a reason from forceStopContainer — both
  // are acceptable; the contract is that ok===true.
  assert.ok(result.reason === undefined || typeof result.reason === 'string');
});

test('deleteJob requests deletion cleanup when BullMQ remove and moveToFailed both fail', async () => {
  // Simulate the production race: the worker owns the active-job lock,
  // so both `remove()` and `moveToFailed()` reject. The container is
  // already torn down by forceStopContainer, so the delete flow should
  // switch to a deletion-request path instead of behaving like a cancel.
  global.__stubJob.remove = async () => { throw new Error('Job is locked'); };
  global.__stubJob.moveToFailed = async () => { throw new Error('Cannot transition job from active to failed'); };
  const result = await deleteJob('j1');
  assert.equal(result.ok, true);
  assert.equal(result.reason, 'delete_requested');
  // Restore happy-path behaviour so subsequent tests (if any) are unaffected.
  global.__stubJob.remove = async () => {};
  global.__stubJob.moveToFailed = async () => {};
});
