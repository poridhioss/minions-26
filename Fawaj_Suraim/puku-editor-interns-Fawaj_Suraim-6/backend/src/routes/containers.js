// Sandbox (container) lifecycle over HTTP.
//   GET    /api/containers             — list ids
//   POST   /api/containers             — create a new sandbox
//   DELETE /api/containers/:id         — destroy a sandbox
//
// Container state lives in `state/registry.js`; creation/destruction
// goes through `services/docker.js` so the route stays a thin shell.

const express = require('express');
const containers = require('../state/registry');
const { createSandbox, destroySandbox } = require('../services/docker');

const router = express.Router();

router.get('/api/containers', (_req, res) => {
  res.json({
    containers: Array.from(containers.keys()).map((id) => ({ id })),
  });
});

router.post('/api/containers', async (_req, res) => {
  try {
    const c = await createSandbox();
    res.status(201).json(c);
  } catch (e) {
    console.error('createSandbox failed:', e);
    res.status(500).json({ error: e.message });
  }
});

router.delete('/api/containers/:id', async (req, res) => {
  try {
    const ok = await destroySandbox(req.params.id);
    res.json({ ok });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

module.exports = router;
