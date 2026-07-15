// src/app.js
// Builds and returns the Express app. server.js wraps it in HTTP + WS;
// tests can mount it on supertest or http directly.

const path = require('path');
const fs = require('fs');
const express = require('express');
const { v4: uuidv4 } = require('uuid');
const { jobQueue, connection } = require('./queue/jobQueue');
const {
  getStatus, cancelJob, listJobs,
  deleteJob, deleteJobs,
} = require('./services/jobStore');
const logStore = require('./services/logStore');
const requireApiKey = require('./middleware/auth');
const csp = require('./middleware/csp');
const log = require('./lib/logger');
const { makeLimiter } = require('./lib/rateLimit');

// Caps on user-supplied fields. A multi-MB `command` would blow up Redis
// queue entries and the worker has to base64-encode / pass it into a
// container, so we reject anything over 64 KB up front with a 400.
const MAX_IMAGE_LEN   = 256;
const MAX_COMMAND_LEN = 64 * 1024;
// Docker reference grammar (OCI distribution): `[registry/]name[:tag][@digest]`.
// We allow lowercase alphanum plus separators (.), (-), (_), (/), (:), (@).
// Anchored on both ends so any stray shell-meta (whitespace, $, ;, etc.) is
// rejected. Without this an attacker could try whitespace-padded "alpine;
// rm -rf /" style payloads; dockerode passes the string straight through.
const SAFE_IMAGE = /^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]{1,128})?(@sha256:[a-f0-9]{64})?$/i;

// Parse an NDJSON string into an array of {ok, line|error} records. Skips
// blank lines and silently drops any line that fails to parse — a single
// corrupted event shouldn't fail the whole /logs endpoint. Used by
// GET /jobs/:id/logs.
function parseNdjson(text) {
  const out = [];
  for (const line of text.split('\n')) {
    if (!line) continue;
    try { out.push(JSON.parse(line)); }
    catch { /* skip corrupted lines */ }
  }
  return out;
}

function buildApp({ subscribers } = {}) {
  const app = express();
  app.use(express.json({ limit: '128kb' }));
  app.use(log.middleware);
  app.use(csp);

  // Serve the static frontend. Layouts we support, in priority order:
  //   1. STATIC_DIR env var (explicit override)
  //   2. <repo>/frontend           (local dev: src/app.js -> ../../frontend)
  //   3. <repo>/backend/public     (legacy)
  //   4. <WORKDIR>/public          (Docker: WORKDIR=/app, src/app.js -> ../public)
  const candidates = [
    process.env.STATIC_DIR,
    path.join(__dirname, '..', '..', 'frontend', 'dist'),
    path.join(__dirname, '..', '..', 'frontend'),
    path.join(__dirname, '..', '..', 'public'),
    path.join(__dirname, '..', 'public'),
  ].filter(Boolean);
  const staticDir = candidates.find((p) => fs.existsSync(path.join(p, 'index.html')));
  if (!staticDir) {
    log.warn('static_dir_not_found', { tried: candidates });
  } else {
    log.info('static_dir_serving', { dir: staticDir });
  }
  app.use(express.static(staticDir || candidates[candidates.length - 1]));

  // Serve index.html for the root path so the UI loads at "/".
  app.get('/', (_req, res, next) => {
    if (!staticDir) return next();
    res.sendFile(path.join(staticDir, 'index.html'));
  });

  // Apply to all /jobs routes
  app.use('/jobs', requireApiKey);

  // Defense in depth: Express normalizes `/jobs/foo%2F..%2Fbar` to
  // `/jobs/bar` BEFORE route matching, so by the time the handler sees
  // req.params.id it's already `bar` — a valid SAFE_ID. That means a
  // carefully crafted URL with `%2F` or `%2E` could escape the :id segment
  // and trigger reads/writes against files outside `logs/`. This middleware
  // compares the raw URL against the decoded path and rejects any :id that
  // contains `/`, `..`, or other traversal characters before the route
  // handlers run. SAFE_ID itself is the source of truth; this is purely
  // a request-shape guard so attackers can't sneak past it via encoded
  // path separators.
  app.use('/jobs', (req, res, next) => {
    // req.path is the decoded version; req.originalUrl is the raw URL the
    // client sent (still URL-encoded). We pull the :id segment from the
    // raw URL and decode it ourselves so a `%2F` in the id is still
    // visible to SAFE_ID. Only check when there's actually a :id segment
    // (i.e. /jobs/<something> or /jobs/<something>/<something>).
    const m = req.originalUrl.match(/^\/jobs\/([^/?#]+)(?:\/([^/?#]+))?/);
    if (!m) return next();
    const idSegment = decodeURIComponent(m[1]);
    const actionSegment = m[2] ? decodeURIComponent(m[2]) : null;
    if (!logStore.SAFE_ID.test(idSegment) || (actionSegment && !logStore.SAFE_ID.test(actionSegment))) {
      return res.status(400).json({ error: 'invalid_id' });
    }
    next();
  });

  // Per-key rate limits on write endpoints. Reads (GET /jobs, /jobs/:id,
  // /jobs/:id/logs) are uncapped — polling clients legitimately hit them on
  // a 1-2s cadence. Writes are gated so a leaked/compromised API key can't
  // spam the queue or mass-delete jobs.
  const writeLimiter = makeLimiter({
    windowMs: 60_000,
    max: Number(process.env.WRITE_RATE_LIMIT_PER_MIN) || 30,
    name: 'writes',
  });
  const deleteLimiter = makeLimiter({
    windowMs: 60_000,
    max: Number(process.env.DELETE_RATE_LIMIT_PER_MIN) || 60,
    name: 'deletes',
  });

  // 1) List recent jobs
  app.get('/jobs', async (_req, res) => {
    try {
      const list = await listJobs({ start: 0, end: 50 });
      res.json({ jobs: list });
    } catch (err) {
      log.error('list_jobs_failed', { err: err.message });
      res.status(500).json({ error: 'list_failed' });
    }
  });

  // 2) Submit a new job
  app.post('/jobs', writeLimiter.middleware, async (req, res) => {
    const { image, command } = req.body || {};
    if (!image || !command) {
      return res.status(400).json({ error: 'image and command are required' });
    }
    if (typeof image !== 'string' || typeof command !== 'string') {
      return res.status(400).json({ error: 'image and command must be strings' });
    }
    if (image.length > MAX_IMAGE_LEN) {
      return res.status(400).json({ error: `image exceeds max length (${MAX_IMAGE_LEN})` });
    }
    if (!SAFE_IMAGE.test(image)) {
      return res.status(400).json({ error: 'image must match [registry/]name[:tag][@sha256:...]' });
    }
    if (command.length > MAX_COMMAND_LEN) {
      return res.status(400).json({ error: `command exceeds max length (${MAX_COMMAND_LEN})` });
    }
    const jobId = uuidv4();
    await jobQueue.add(
      'run',
      { jobId, image, command },
      {
        jobId,
        attempts: 3,
        backoff: { type: 'exponential', delay: 1000 },
        removeOnComplete: { age: 3600, count: 1000 },
        removeOnFail: { age: 24 * 3600 },
      }
    );
    res.status(202).json({ jobId });
  });

  // 3) Get one job's status (mapped to a 'cancelled' state for nicer UI rendering)
  app.get('/jobs/:id', async (req, res) => {
    const status = await getStatus(req.params.id);
    if (status.state === 'unknown') return res.status(404).json({ error: 'not_found' });
    res.json(status);
  });

  // 4) Delete one job (kills container + drops queue entry + deletes logs)
  app.delete('/jobs/:id', deleteLimiter.middleware, async (req, res) => {
    try {
      const out = await deleteJob(req.params.id);
      if (!out.ok) {
        log.warn('delete_job_not_ok', { jobId: req.params.id, reason: out.reason });
        return res.status(500).json({ error: 'delete_failed', reason: out.reason });
      }
      await logStore.remove(req.params.id).catch(() => {});
      res.json(out);
    } catch (err) {
      if (err.name === 'InvalidJobIdError') {
        return res.status(400).json({ error: 'invalid_id' });
      }
      log.error('delete_job_failed', { err: err.message });
      res.status(500).json({ error: 'delete_failed' });
    }
  });

  // 5) Bulk delete
  app.post('/jobs/delete', deleteLimiter.middleware, async (req, res) => {
    const ids = Array.isArray(req.body?.ids) ? req.body.ids : [];
    if (ids.length === 0) return res.json({ deleted: 0 });
    if (!ids.every((id) => typeof id === 'string')) {
      return res.status(400).json({ error: 'ids must be an array of strings' });
    }
    try {
      const out = await deleteJobs(ids);
      await Promise.all(ids.map((id) => logStore.remove(id).catch(() => {})));
      res.json(out);
    } catch (err) {
      log.error('delete_jobs_failed', { err: err.message });
      res.status(500).json({ error: 'delete_failed' });
    }
  });

  // 6) Cancel a running job (force-kills container + sets Redis cancel key)
  app.post('/jobs/:id/cancel', async (req, res) => {
    try {
      const result = await cancelJob(req.params.id);
      if (!result.ok) return res.status(409).json(result);
      res.json(result);
    } catch (err) {
      log.error('cancel_job_failed', { err: err.message });
      res.status(500).json({ error: 'cancel_failed' });
    }
  });

  // 7) Read full persisted log (NDJSON, newest-last). Tolerant of corrupted
  //    lines so a single bad event doesn't 500 the whole endpoint.
  app.get('/jobs/:id/logs', async (req, res) => {
    try {
      const content = await logStore.read(req.params.id);
      if (content === null) return res.status(404).json({ error: 'no_logs' });
      res.json({ jobId: req.params.id, lines: parseNdjson(content) });
    } catch (err) {
      if (err.name === 'InvalidJobIdError') {
        return res.status(400).json({ error: 'invalid_id' });
      }
      throw err;
    }
  });

  // Health endpoint (no auth) for orchestrators / load balancers.
  app.get('/healthz', (_req, res) => res.json({ status: 'ok' }));

  return app;
}

module.exports = { buildApp, connection, jobQueue };
