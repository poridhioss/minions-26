// src/services/jobStore.js
const { Queue } = require('bullmq');
const Redis = require('ioredis');
const Docker = require('dockerode');
const { connection } = require('../queue/jobQueue');

const queue = new Queue('container-jobs', { connection });
const redis = new Redis(connection);
// Log + keep running on Redis disconnects; otherwise the EventEmitter throws
// on the next tick and takes the API process down. All callers in this
// module already .catch() redis errors so individual requests degrade
// gracefully even when Redis is down.
redis.on('error', (err) => {
  process.stderr.write(JSON.stringify({
    ts: new Date().toISOString(),
    level: 'error',
    msg: 'redis_jobstore_error',
    err: err.message,
  }) + '\n');
});
// Used by cancel/delete to forcibly tear down a container whose owning
// worker is wedged or has lost its lock. Talks straight to the Docker
// daemon so the API doesn't need a back-channel into worker state.
const docker = new Docker();
const cancelKey = (jobId) => `job-cancel:${jobId}`;
const deleteKey = (jobId) => `job-delete:${jobId}`;
const containerKey = (jobId) => `job-container:${jobId}`;

// Kill any container the worker registered for this job, regardless of
// whether the worker is responsive. Best-effort: missing registry entry,
// docker socket errors, or already-stopped containers all resolve to
// `ok: true` so callers don't treat cleanup hiccups as user-facing
// failures.
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

  // A user-initiated cancel surfaces two ways depending on which worker
  // version ran the job:
  //   - The new cancel-recheck path (this PR) throws after re-checking the
  //     cancel key, so BullMQ moves the job to `failed` with
  //     failedReason="cancelled by user".
  //   - Older workers (or jobs that ran before the patch) might still have
  //     it as `completed` with returnvalue.statusCode=137 (SIGKILL).
  // Map both to `cancelled` so the UI can render the right state instead
  // of showing "completed" with a confusing 137 exit code.
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
  // BullMQ returns oldest-first; the sidebar wants most-recent-first.
  return enriched
    .sort((a, b) => Date.parse(b.queuedAt || 0) - Date.parse(a.queuedAt || 0))
    .slice(0, end - start + 1);
}

async function deleteJob(jobId) {
  // Always tear down the container first; the user wants the job gone
  // regardless of what state BullMQ thinks it's in.
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
      // Worker holds the active-job lock; both BullMQ paths fail. The container
      // is already gone, so report success — the user's intent is satisfied.
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
  // Tear down the container first, before checking queue state — the user
  // wants the job gone even if BullMQ has already TTL'd its entry.
  await forceStopContainer(jobId);

  const job = await queue.getJob(jobId);
  if (!job) return { ok: true, reason: 'already_gone' };

  const state = await job.getState();
  // Idempotent: if the job is already terminal, the cancel intent is already
  // satisfied. Returning ok lets the UI drop the "cancelling…" spinner.
  if (state === 'completed' || state === 'failed') {
    return { ok: true, reason: 'already_finished' };
  }

  try {
    await job.moveToFailed(new Error('cancelled by user'), true);
    return { ok: true };
  } catch (err) {
    // Worker holds the active-job lock; the moveToFailed is rejected but the
    // container is already gone. Set a cancel-key so the worker's 500ms poll
    // picks it up and transitions the job to failed.
    await redis.set(cancelKey(jobId), '1', 'EX', 300);
    return { ok: true, reason: 'cancel_requested' };
  }
}

module.exports = { getStatus, cancelJob, listJobs, deleteJob, deleteJobs, forceStopContainer };