// test/jobStore.test.js
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
