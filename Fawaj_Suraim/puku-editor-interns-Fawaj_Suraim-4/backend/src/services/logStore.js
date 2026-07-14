const fs = require('fs');
const path = require('path');
const { mkdirp } = require('mkdirp');

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

async function append(jobId, line) {
  await fs.promises.mkdir(LOG_DIR, { recursive: true });
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