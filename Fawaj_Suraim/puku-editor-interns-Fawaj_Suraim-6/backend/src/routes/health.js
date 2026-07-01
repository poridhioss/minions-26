// Health + version probe. Used by the frontend to check the server is
// up and to surface the active sandbox image (so the user can see
// whether they got the optimised image or the dev fallback).

const express = require('express');
const { SANDBOX_IMAGE } = require('../config');
const containers = require('../state/registry');

const router = express.Router();

router.get('/api/health', (_req, res) => {
  res.json({ ok: true, containers: containers.size, image: SANDBOX_IMAGE });
});

module.exports = router;
