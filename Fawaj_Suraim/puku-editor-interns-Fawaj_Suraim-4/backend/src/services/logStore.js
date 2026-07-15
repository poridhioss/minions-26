const fs = require('fs');
const path = require('path');
const log = require('../lib/logger');

const LOG_DIR = path.join(process.cwd(), 'logs');

// Caller-supplied jobIds come straight from URL params. Without this check,
// `path.join(LOG_DIR, '../../etc/passwd' + '.log')` happily resolves to
// /etc/passwd.log and exposes / deletes files outside `logs/`.
const SAFE_ID = /^[A-Za-z0-9_-]+$/;

class InvalidJobIdError extends Error {
  constructor(jobId) {
    super(`invalid jobId: ${jobId}`);
    this.name = 'InvalidJobIdError';
  }
}

function pathFor(jobId) {
  if (typeof jobId !== 'string' || !SAFE_ID.test(jobId)) {
    throw new InvalidJobIdError(jobId);
  }
  return path.join(LOG_DIR, `${jobId}.log`);
}

// Memoise the directory bootstrap. Concurrent append() callers (worker
// concurrency=2) all await the same promise; subsequent appends skip the
// syscalls entirely. A failed bootstrap stays failed for the lifetime of
// the process — operators see the error in logs and restart the worker
// after fixing permissions, rather than silent data loss from a runtime
// rm -rf.
let readyPromise;
function ensureWritable() {
  if (!readyPromise) {
    readyPromise = (async () => {
      await fs.promises.mkdir(LOG_DIR, { recursive: true });
      await fs.promises.access(LOG_DIR, fs.constants.W_OK);
    })();
  }
  return readyPromise;
}

async function append(jobId, line) {
  try {
    await ensureWritable();
  } catch (err) {
    log.error('log_dir_unwritable', { dir: LOG_DIR, err: err.message });
    throw err;
  }
  await fs.promises.appendFile(pathFor(jobId), line, 'utf8');
}

async function read(jobId) {
  const file = pathFor(jobId);
  if (!fs.existsSync(file)) return null;
  return fs.promises.readFile(file, 'utf8');
}

async function remove(jobId) {
  const file = pathFor(jobId);
  try { await fs.promises.unlink(file); }
  catch (err) { if (err.code !== 'ENOENT') throw err; }
}

module.exports = { append, read, remove, pathFor, SAFE_ID };