// Docker sandbox lifecycle: image resolution, container create/destroy.
//
// The shared `docker` client connects to the host's `/var/run/docker.sock`.
// All sandbox state lives in `state/registry.js` — this service just
// drives dockerode and updates the registry.
//
// We deliberately *don't* bind-mount the host filesystem; the sandbox
// reads/writes files via `services/sandbox-fs.js` (which shells into
// the container). That keeps the editor able to run against any
// container, including remote ones, without per-host volume plumbing.

const Docker = require('dockerode');
const {
  SANDBOX_IMAGE,
  FALLBACK_IMAGE,
  WORKDIR,
  SANDBOX_USER,
  AUTO_CLEANUP,
} = require('../config');
const containers = require('../state/registry');

const docker = new Docker({ socketPath: '/var/run/docker.sock' });

/**
 * Make sure the requested image is available locally. If it isn't, fall
 * back to the dev fallback (`node:20-slim`) so the server still boots
 * before `Dockerfile.override` has been built.
 *
 * Permission / connection errors are surfaced as-is — the most common
 * cause on a fresh deploy is the host docker socket being unreadable
 * (wrong group membership) and silently re-trying the fallback just
 * hides the real error from the user.
 */
async function ensureImage(image) {
  try {
    await docker.getImage(image).inspect();
    return image;
  } catch (e) {
    // Anything that isn't a "this image is missing" 404 from the
    // docker daemon is a transport / permission problem and should
    // not be masked by a fallback retry. Common offenders:
    //   - EACCES on /var/run/docker.sock (group_add not set)
    //   - ECONNREFUSED (docker daemon not running)
    //   - ENOENT (socket path doesn't exist on the host)
    if (e.statusCode !== 404) {
      throw e;
    }
    if (image === SANDBOX_IMAGE) {
      console.warn(`[sandbox] '${SANDBOX_IMAGE}' not found, falling back to '${FALLBACK_IMAGE}'`);
      // Same isolation here: if the fallback also 404s, surface
      // that to the user. The previous implementation re-threw a
      // generic "not available" message and lost the original 404.
      await ensureImage(FALLBACK_IMAGE);
      return FALLBACK_IMAGE;
    }
    throw new Error(`Docker image '${image}' not available locally and no fallback.`);
  }
}

/**
 * Spawn a fresh sandbox and register it. Returns the docker id and the
 * human-friendly container name.
 *
 * Security defaults (overridable via env in config/index.js):
 *   - Runs as the unprivileged `developer` user baked into
 *     backend/Dockerfile.sandbox. Set SANDBOX_USER='' to run as root
 *     (only safe for throwaway CI sandboxes).
 *   - AutoRemove:true so the container is reaped by the Docker daemon
 *     if the orchestrator crashes. Set AUTO_CLEANUP=false in
 *     config/index.js for long-lived debug sandboxes.
 *   - Capped at 0.5 CPU + 512MB RAM.
 */
async function createSandbox() {
  const image = await ensureImage(SANDBOX_IMAGE);

  const container = await docker.createContainer({
    Image: image,
    // Kick off a long-lived bash so the first `exec` we do later (for
    // file ops or terminal PTYs) inherits a sane working dir + prompt.
    Cmd: ['/bin/sh', '-c', 'mkdir -p /workspace && cd /workspace && exec /bin/bash'],
    Tty: true,
    OpenStdin: true,
    StdinOnce: false,
    User: SANDBOX_USER || undefined,
    WorkingDir: WORKDIR,
    Env: [
      'PS1=\\u@sandbox:\\w\\$ ',
      'TERM=xterm-256color',
    ],
    HostConfig: {
      // `--rm` equivalent: the daemon reaps the container once it
      // stops. Pairs with destroySandbox() so we never leave orphans.
      AutoRemove: AUTO_CLEANUP,
      Memory: 512 * 1024 * 1024,
      NanoCpus: 500_000_000, // 0.5 CPU
      NetworkMode: 'bridge',
    },
  });

  await container.start();
  const info = await container.inspect();
  containers.set(container.id, { container, createdAt: Date.now() });
  return { id: container.id, name: info.Name.replace(/^\//, '') };
}

/**
 * Kill + remove a sandbox by id. Returns true if it existed, false if
 * it was already gone. Idempotent: never throws on a missing entry.
 *
 * If AutoRemove is on (the default), the daemon reaps the container
 * itself once it stops; we just need to call `stop` and let the
 * daemon handle the rest. `remove({ force: true })` is still safe to
 * call — dockerode is happy if the container is already gone.
 */
async function destroySandbox(id) {
  const entry = containers.get(id);
  if (!entry) return false;
  try {
    await entry.container.kill().catch(() => {});
    if (!AUTO_CLEANUP) {
      await entry.container.remove({ force: true });
    }
  } finally {
    containers.delete(id);
  }
  return true;
}

module.exports = {
  docker,
  ensureImage,
  createSandbox,
  destroySandbox,
};
