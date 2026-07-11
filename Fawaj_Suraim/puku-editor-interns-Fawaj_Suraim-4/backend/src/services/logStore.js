// src/services/logStore.js
const fs = require('fs');
const path = require('path');
// mkdirp v3 exports named functions; v1/v2 exported a default callable.
// We destructure the specific function we need so the call site is the same shape.
const { mkdirp } = require('mkdirp');

const LOG_DIR = path.join(process.cwd(), 'logs');

function pathFor(jobId) {
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

module.exports = { append, read, pathFor };