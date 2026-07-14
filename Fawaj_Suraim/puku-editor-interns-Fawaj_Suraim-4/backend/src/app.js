// src/app.js
// Builds and returns the Express app. server.js wraps it in HTTP + WS;
// tests can mount it on supertest or http directly.

const express = require('express');
const { jobQueue, connection } = require('./queue/jobQueue');
const { getStatus, cancelJob, listJobs, deleteJob, deleteJobs } = require('./services/jobStore');
const logStore = require('./services/logStore');
const requireApiKey = require('./middleware/auth');
const csp = require('./middleware/csp');
const log = require('./lib/logger');

function buildApp({ subscribers } = {}) {
  const app = express();
  app.use(express.json());
  app.use(log.middleware);
  app.use(csp);

  const path = require('path');
  const fs = require('fs');
  // Serve the static frontend. Layouts we support, in priority order:
  //   1. STATIC_DIR env var (explicit override)
  //   2. <repo>/frontend           (local dev: src/app.js -> ../../frontend)
  //   3. <repo>/backend/public     (legacy)
  //   4. <WORKDIR>/public          (Docker: WORKDIR=/app, src/app.js -> ../public)
  const candidates = [
    process.env.STATIC_DIR,
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

  // 1) Submit a new job
  app.get('/jobs', async (_req, res) => {
    try {
      const list = await listJobs({ start: 0, end: 50 });
      res.json({ jobs: list });
    } catch (err) {
      log.error('list_jobs_failed', { err: err.message });
      res.status(500).json({ error: 'list_failed' });
    }
  });

  app.post('/jobs', async (req, res) => {
    const { image, command } = req.body;
    if (!image || !command) {
      return res.status(400).json({ error: 'image and command are required' });
    }
    const jobId = require('uuid').v4();
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

  app.get('/jobs/:id', async (req, res) => {
    const status = await getStatus(req.params.id);
    if (status.state === 'unknown') return res.status(404).json({ error: 'not_found' });
    res.json(status);
  });

  app.delete('/jobs/:id', async (req, res) => {
    try {
      const out = await deleteJob(req.params.id);
      
      if (!out.ok) {
        log.warn('delete_job_not_ok', { jobId: req.params.id, reason: out.reason });
        return res.status(500).json({ error: 'delete_failed', reason: out.reason });
      }
      if (out.reason === 'cleanup_partial') {
        
        log.warn('delete_job_cleanup_partial', { jobId: req.params.id, detail: out.detail });
      }
      await logStore.remove(req.params.id).catch(() => {});
      res.json(out);
    } catch (err) {
      log.error('delete_job_failed', { err: err.message });
      res.status(500).json({ error: 'delete_failed' });
    }
  });

  app.post('/jobs/delete', async (req, res) => {
    const ids = Array.isArray(req.body?.ids) ? req.body.ids : [];
    if (ids.length === 0) return res.json({ deleted: 0 });
    try {
      const out = await deleteJobs(ids);
      await Promise.all(ids.map((id) => logStore.remove(id).catch(() => {})));
      res.json(out);
    } catch (err) {
      log.error('delete_jobs_failed', { err: err.message });
      res.status(500).json({ error: 'delete_failed' });
    }
  });

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

  app.get('/jobs/:id/logs', async (req, res) => {
    const content = await logStore.read(req.params.id);
    if (content === null) return res.status(404).json({ error: 'no_logs' });
    const lines = content.split('\n').filter(Boolean).map((l) => JSON.parse(l));
    res.json({ jobId: req.params.id, lines });
  });

  // Health endpoint (no auth) for orchestrators / load balancers.
  app.get('/healthz', (_req, res) => res.json({ status: 'ok' }));

  return app;
}

module.exports = { buildApp, connection, jobQueue };
