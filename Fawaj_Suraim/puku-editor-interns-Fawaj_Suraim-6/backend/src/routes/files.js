// File API: tree listing, read, write, delete, and a one-shot exec for
// shell commands the editor fires (rename, mkdir, mv, etc.).
//
//   GET    /api/containers/:id/tree?path=DIR
//   GET    /api/containers/:id/files?path=PATH
//   POST   /api/containers/:id/files        { path, content }
//   DELETE /api/containers/:id/files?path=PATH
//   POST   /api/containers/:id/exec         { command }
//
// Every handler resolves the container from `state/registry.js` first
// so a stale id 404s consistently. The actual work is in
// `services/sandbox-fs.js`.

const express = require('express');
const { WORKDIR } = require('../config');
const containers = require('../state/registry');
const {
  readFile,
  writeFile,
  listDir,
  deletePath,
  execIn,
} = require('../services/sandbox-fs');

const router = express.Router();

router.get('/api/containers/:id/tree', async (req, res) => {
  const entry = containers.get(req.params.id);
  if (!entry) return res.status(404).json({ error: 'Container not found' });
  const dir = req.query.path || WORKDIR;
  try {
    res.json(await listDir(entry.container, dir));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

router.get('/api/containers/:id/files', async (req, res) => {
  const entry = containers.get(req.params.id);
  if (!entry) return res.status(404).json({ error: 'Container not found' });
  const file = req.query.path;
  if (!file) return res.status(400).json({ error: 'path required' });
  try {
    const content = await readFile(entry.container, file);
    res.json({ path: file, content });
  } catch (e) {
    if (e.code === 'ENOENT') return res.status(404).json({ error: e.message });
    res.status(500).json({ error: e.message });
  }
});

router.post('/api/containers/:id/files', async (req, res) => {
  const entry = containers.get(req.params.id);
  if (!entry) return res.status(404).json({ error: 'Container not found' });
  const { path: file, content } = req.body || {};
  if (!file) return res.status(400).json({ error: 'path required' });
  try {
    await writeFile(entry.container, file, content ?? '');
    res.json({ ok: true, path: file });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

router.delete('/api/containers/:id/files', async (req, res) => {
  const entry = containers.get(req.params.id);
  if (!entry) return res.status(404).json({ error: 'Container not found' });
  const file = req.query.path;
  if (!file) return res.status(400).json({ error: 'path required' });
  try {
    await deletePath(entry.container, file);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

router.post('/api/containers/:id/exec', async (req, res) => {
  const entry = containers.get(req.params.id);
  if (!entry) return res.status(404).json({ error: 'Container not found' });
  const { command } = req.body || {};
  if (!command) return res.status(400).json({ error: 'command required' });
  try {
    const out = await execIn(entry.container, command);
    res.json(out);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

module.exports = router;
