// src/services/jobStore.js
const { Queue } = require('bullmq');
const Redis = require('ioredis');
const Docker = require('dockerode');
const { connection } = require('../queue/jobQueue');

const queue = new Queue('container-jobs', { connection });
const redis = new Redis(connection);
const docker = new Docker();
const cancelKey = (jobId) => `job-cancel:${jobId}`;
const deleteKey = (jobId) => `job-delete:${jobId}`;
const containerKey = (jobId) => `job-container:${jobId}`;

async function forceStopContainer(jobId) {
  const id = await redis.get(containerKey(jobId)).catch(() => null);
  if (!id) return { ok: true, reason: 'no_container_registered' };
  try {
    const c = docker.getContainer(id);
    try { await c.kill(); } catch (_) { /* may already be stopped */ }
    try { await c.remove({ force: true }); } catch (_) { /* may already be gone */ }
    await redis.del(containerKey(jobId)).catch(() => {});
    return { ok: true };
  } catch (err) {
    return { ok: false, reason: err.message };
  }
}

async function getStatus(jobId) {
  if ((await redis.get(deleteKey(jobId))) === '1') {
    return { state: 'deleted', jobId };
  }

  const job = await queue.getJob(jobId);
  if (!job) return { state: 'unknown' };

  let state = await job.getState(); // 'waiting' | 'active' | 'completed' | 'failed' | 'delayed'

  const exitCode =
    job.returnvalue && typeof job.returnvalue.statusCode === 'number'
      ? job.returnvalue.statusCode
      : null;

  const startedAt = job.processedOn ? new Date(job.processedOn).toISOString() : null;
  const finishedAt = job.finishedOn ? new Date(job.finishedOn).toISOString() : null;
  const queuedAt = job.timestamp ? new Date(job.timestamp).toISOString() : null;

  const durationMs =
    job.processedOn && job.finishedOn ? job.finishedOn - job.processedOn : null;

  if (
    (state === 'failed' && /cancelled by user/i.test(job.failedReason || '')) ||
    (state === 'completed' && exitCode === 137)
  ) {
    state = 'cancelled';
  }

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

async function listJobs({ start = 0, end = 50 } = {}) {
 
  const jobs = await queue.getJobs(['waiting', 'active', 'completed', 'failed', 'delayed'], start, end);

  const enriched = await Promise.all(
    jobs
      .filter(Boolean)
      .map(async (j) => {
        const s = await getStatus(j.id);
        return {
          jobId: j.id,
          image: j.data?.image || null,
          command: j.data?.command || null,
          queuedAt: s.queuedAt,
          state: s.state,
          exitCode: s.exitCode,
          startedAt: s.startedAt,
          finishedAt: s.finishedAt,
          durationMs: s.durationMs,
          attemptsMade: s.attemptsMade,
          failedReason: s.failedReason,
        };
      })
  );
  return enriched
    .sort((a, b) => Date.parse(b.queuedAt || 0) - Date.parse(a.queuedAt || 0))
    .slice(0, end - start + 1);
}

async function deleteJob(jobId) {

  const stop = await forceStopContainer(jobId);

  const job = await queue.getJob(jobId);

  if (!job) {
    await redis.set(deleteKey(jobId), '1', 'EX', 300).catch(() => {});
    return { ok: true, reason: stop.ok ? 'already_gone' : 'already_gone_partial', container: stop.reason };
  }

  try {
    await job.remove();
    await redis.set(deleteKey(jobId), '1', 'EX', 300).catch(() => {});
    return { ok: true, reason: stop.reason };
  } catch (_err) {
    try {
      await job.moveToFailed(new Error('deleted by user'), true);
      try { await job.remove(); } catch (_) { /* may already be gone */ }
      await redis.set(deleteKey(jobId), '1', 'EX', 300).catch(() => {});
      return { ok: true, reason: 'delete_requested' };
    } catch (e2) {

      await redis.set(deleteKey(jobId), '1', 'EX', 300).catch(() => {});
      return { ok: true, reason: 'delete_requested', container: stop.reason, detail: e2.message };
    }
  }
}

async function deleteJobs(ids) {
  const results = await Promise.all(ids.map((id) => deleteJob(id)));
  return { deleted: results.filter((r) => r.ok).length, results };
}

async function cancelJob(jobId) {

  await forceStopContainer(jobId);

  const job = await queue.getJob(jobId);

  if (!job) return { ok: true, reason: 'already_gone' };

  const state = await job.getState();

  if (state === 'completed' || state === 'failed') {
    return { ok: true, reason: 'already_finished' };
  }

  try {
    await job.moveToFailed(new Error('cancelled by user'), true);
    return { ok: true };
  } catch (err) {
  
    if (state === 'active' && /lock mismatch/i.test(err.message)) {
      await redis.set(cancelKey(jobId), '1', 'EX', 300);
      return { ok: true, reason: 'cancel_requested' };
    }
  
    await redis.set(cancelKey(jobId), '1', 'EX', 300);
    return { ok: true, reason: 'cancel_requested' };
  }
}

module.exports = { getStatus, cancelJob, listJobs, deleteJob, deleteJobs, forceStopContainer };