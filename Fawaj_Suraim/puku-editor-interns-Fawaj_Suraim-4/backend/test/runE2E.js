#!/usr/bin/env node
// Runs the e2e test suite inside the docker-compose stack so it can
// reach redis:6379 + the running worker. Used by `npm run test:e2e`.

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const repoRoot = path.resolve(__dirname, '..', '..');
const composeFile = path.join(repoRoot, 'docker-compose.yml');

function step(label, cmd, args) {
  console.log(`[test:e2e] ${label}`);
  const res = spawnSync(cmd, args, { stdio: 'inherit', cwd: repoRoot });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

// 1) Bring the long-running stack up if it isn't already.
const ps = spawnSync('docker', ['compose', '-f', composeFile, 'ps', '--quiet'], {
  cwd: repoRoot, encoding: 'utf8',
});
const isUp = (ps.stdout || '').trim().length > 0;
if (!isUp) step('stack not running — bringing it up', 'docker', ['compose', '-f', composeFile, 'up', '-d']);
else step('stack already up', 'docker', ['compose', '-f', composeFile, 'ps']);

// 2) Run the test container once (ephemeral, --no-deps keeps worker+server untouched).
step('running test-runner', 'docker', ['compose', '-f', composeFile, 'run', '--rm', '--no-deps', 'test-runner']);