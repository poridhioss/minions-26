// src/queue/jobQueue.js
const { Queue } = require('bullmq');
require('dotenv').config();

// Fail fast with a clear message if REDIS_URL isn't set. Without this the
// `new URL(undefined)` below throws a cryptic "Invalid URL" error and the
// process exits without telling the operator what's missing.
const REDIS_URL = process.env.REDIS_URL;
if (!REDIS_URL) {
  // Use stderr directly; logger may not be loaded yet and we want this to
  // be the very first thing printed on startup.
  process.stderr.write(
    JSON.stringify({
      ts: new Date().toISOString(),
      level: 'error',
      msg: 'missing_redis_url',
      hint: 'Set REDIS_URL in backend/.env (e.g. redis://127.0.0.1:6379).',
    }) + '\n'
  );
  process.exit(1);
}

const parsed = new URL(REDIS_URL);
const connection = {
  host: parsed.hostname,
  port: Number(parsed.port) || 6379,
};

const jobQueue = new Queue('container-jobs', { connection });

module.exports = { jobQueue, connection };