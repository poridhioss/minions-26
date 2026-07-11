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

    const publish = (event) =>
      pub.publish(channel, JSON.stringify(event));
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
        // Resource limits
        Memory: 256 * 1024 * 1024,  // 256 MB hard cap
        NanoCpus: 500_000_000,      // 0.5 vCPU
        PidsLimit: 64,              // 64 processes max
        // Network: fully isolated. Flip to 'bridge' if you need egress and
        // understand the implications.
        NetworkMode: 'none',
        // Defense in depth
        ReadonlyRootfs: true,        // can't write anywhere except tmpfs mounts
        AutoRemove: true,
        CapDrop: ['ALL'],            // start with zero capabilities
        SecurityOpt: ['no-new-privileges:true'],
        Tmpfs: {
          // Two small writable tmpfs mounts for /tmp and /run; size in bytes.
          // uid/gid default to 0 (root) so any image works; tighten if you control the image.
          '/tmp': 'size=64m',
          '/run': 'size=16m',
        },
        // Optional: ulimits to cap open files / fds inside the container.
        // 1024 is enough for busybox sh + a handful of helpers.
        Ulimits: [
          { Name: 'nofile', Soft: 1024, Hard: 1024 },
          { Name: 'nproc',  Soft: 64,   Hard: 64   },
        ],
      },
    };
    // Only set User if the operator explicitly asked for one. Many minimal
    // images (alpine, distroless, scratch) don't include a UID 1000 user, and
    // Docker will then fail with "no such user" before the process starts.
    if (process.env.JOB_USER) containerSpec.User = process.env.JOB_USER;

    const container = await docker.createContainer(containerSpec);
    await container.start();
    containersByJobId.set(jobId, container);

    // Demux stream so stdout and stderr stay separate.
    // Buffer each stream so a chunk split mid-line still produces whole-line records.
    container.logs(
      { follow: true, stdout: true, stderr: true },
      (err, stream) => {
        if (err) {
          publish({ type: 'error', data: err.message });
          logLine({ type: 'error', data: err.message });
          return;
        }

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
            write: (chunk) => {
              buf += chunk.toString();
              flush(false);
            },
            end: () => flush(true),
          };
        };

        const stdoutW = makeLineBufferedWriter('stdout');
        const stderrW = makeLineBufferedWriter('stderr');

        docker.modem.demuxStream(
          stream,
          { write: (chunk) => stdoutW.write(chunk), end: () => stdoutW.end() },
          { write: (chunk) => stderrW.write(chunk), end: () => stderrW.end() }
        );
      }
    );

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

    if (timedOut) {
      // Throw so BullMQ triggers retry with backoff; if all attempts fail, the job is marked failed.
      throw new Error(`job_timed_out_after_${timeoutMs}ms`);
    }

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

  // worker.close() finishes the current job (or rejects after attempts) before resolving.
  try { await worker.close(); } catch (e) { log.error('worker_close_error', { err: e.message }); }

  // If containers are still alive (shouldn't happen, but be defensive), kill them.
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