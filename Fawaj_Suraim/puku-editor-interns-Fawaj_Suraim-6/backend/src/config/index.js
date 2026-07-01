// Centralised server configuration. Keep this file dependency-free so it
// can be imported by every other module (services, routes, boot) without
// risk of circular requires.

const PORT = process.env.PORT || 3001;
const SANDBOX_IMAGE = process.env.SANDBOX_IMAGE || 'replit-sandbox';
const FALLBACK_IMAGE = 'node:20-slim';
const WORKDIR = '/workspace';

// UID/GID of the unprivileged `developer` user baked into
// backend/Dockerfile.sandbox. The orchestrator passes this on every
// `createContainer` + `exec` so user-owned files line up with the
// file-sync API. Override at build/run time if you ship a custom
// image with a different account.
const SANDBOX_USER = process.env.SANDBOX_USER || 'developer';

// When true (default), the container is created with --rm equivalent
// (AutoRemove:true) and is destroyed on socket disconnect. Flip to
// false in CI / debugging scenarios where you want to keep the
// workspace around after the client goes away.
const AUTO_CLEANUP = process.env.AUTO_CLEANUP !== 'false';

module.exports = {
  PORT,
  SANDBOX_IMAGE,
  FALLBACK_IMAGE,
  WORKDIR,
  SANDBOX_USER,
  AUTO_CLEANUP,
};
