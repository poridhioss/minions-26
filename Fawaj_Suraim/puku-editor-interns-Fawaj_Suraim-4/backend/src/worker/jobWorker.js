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
const cancelKey = (jobId) => `job-cancel:${jobId}`;
const deleteKey = (jobId) => `job-delete:${jobId}`;

const containerKey = (jobId) => `job-container:${jobId}`;

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

    if ((await pub.get(cancelKey(jobId))) === '1') {
      await job.moveToFailed(new Error('cancelled by user'), true).catch(() => {});
      throw new Error('cancelled by user');
    }
    if ((await pub.get(deleteKey(jobId))) === '1') {
      await job.remove().catch(() => {});
      await pub.del(deleteKey(jobId)).catch(() => {});
      await logStore.remove(jobId).catch(() => {});
      return { statusCode: 137, deleted: true };
    }

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
        PidsLimit: 64,              // 64 
        NetworkMode: 'none',
        // Defense in depth
        ReadonlyRootfs: true,        // can't write anywhere except tmpfs mounts
        AutoRemove: true,
        CapDrop: ['ALL'],            // start with zero capabilities
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

    pub.set(containerKey(jobId), container.id, 'EX', 3600).catch((err) =>
      log.error('container_key_failed', { jobId, err: err.message })
    );


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


    const timeoutMs = Number(process.env.JOB_TIMEOUT_MS) || 5 * 60 * 1000;
    let timedOut = false;
    const waitPromise = container.wait();
    const timer = setTimeout(async () => {
      timedOut = true;
      try { await container.kill(); } catch (_) {}
      publish({ type: 'log', stream: 'system', data: `[timeout] killed after ${timeoutMs}ms\n` });
      logLine({ type: 'log', stream: 'system', data: `[timeout] killed after ${timeoutMs}ms\n` });
    }, timeoutMs);

    let interval;
    const outcome = await Promise.race([
      waitPromise.then((result) => ({ kind: 'exit', result })),
      new Promise((resolve) => {
        interval = setInterval(async () => {
          if ((await pub.get(cancelKey(jobId))) === '1') {
            clearInterval(interval);
            resolve({ kind: 'cancel' });
            return;
          }
          if ((await pub.get(deleteKey(jobId))) === '1') {
            clearInterval(interval);
            resolve({ kind: 'delete' });
          }
        }, 500);
      }),
    ]);
    clearTimeout(timer);
    clearInterval(interval);

    const deleteRequested = (await pub.get(deleteKey(jobId))) === '1';
    const cancelled = (
      outcome.kind === 'cancel' ||
      outcome.kind === 'delete' ||
      (await pub.get(cancelKey(jobId))) === '1' ||
      deleteRequested
    );

    if (cancelled) {
      try { await container.kill(); } catch (_) {}
      try { await container.remove({ force: true }); } catch (_) {}
      containersByJobId.delete(jobId);
      await pub.del(cancelKey(jobId));
      await pub.del(deleteKey(jobId));
      if (deleteRequested) {
        await job.remove().catch(() => {});
        await logStore.remove(jobId).catch(() => {});
        publish({ type: 'log', stream: 'system', data: '[deleted by user]\n' });
        logLine({ type: 'log', stream: 'system', data: '[deleted by user]\n' });
        return { statusCode: 137, deleted: true };
      }
      const message = 'cancelled by user';
      publish({ type: 'log', stream: 'system', data: `[${message}]\n` });
      logLine({ type: 'log', stream: 'system', data: `[${message}]\n` });
      await job.moveToFailed(new Error(message), true).catch(() => {});
      throw new Error(message);
    }

    const result = outcome.result;

    publish({ type: 'exit', jobId, statusCode: result.StatusCode, timedOut });
    logLine({ type: 'exit', jobId, statusCode: result.StatusCode, timedOut });
    await pub.del(cancelKey(jobId));

    if (timedOut) {
      
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
  pub.del(containerKey(jobId)).catch(() => {});
});

worker.on('completed', (job, ret) => {
  log.info('job_completed', { jobId: job.data.jobId, returnvalue: ret });

  pub.del(containerKey(job.data.jobId)).catch(() => {});
});

log.info('worker_started', { queue: 'container-jobs' });

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