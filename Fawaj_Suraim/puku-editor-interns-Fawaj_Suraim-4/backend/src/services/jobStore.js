// src/services/jobStore.js
const { Queue } = require('bullmq');
const { connection } = require('../queue/jobQueue');

const queue = new Queue('container-jobs', { connection });

async function getStatus(jobId) {
  const job = await queue.getJob(jobId);
  if (!job) return { state: 'unknown' };

  const state = await job.getState(); // 'waiting' | 'active' | 'completed' | 'failed' | 'delayed'

  // Shape the result so callers see exactly what they need, in one round-trip.
  // returnvalue is set by the worker to { statusCode, ... }; pull statusCode out.
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

  // Move to failed so the worker logic can react on 'failed' event
  await job.moveToFailed(new Error('cancelled by user'), true);
  return { ok: true };
}

module.exports = { getStatus, cancelJob };