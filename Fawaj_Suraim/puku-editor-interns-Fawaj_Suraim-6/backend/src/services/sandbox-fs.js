// Filesystem + exec helpers that run *inside* a sandbox container.
//
// Every helper takes a dockerode `Container` (from registry.js) and
// shells out via `/bin/sh -c`. This is intentionally simple: the sandbox
// is the source of truth, and shelling into it means the file API
// matches what the user sees in the editor's terminal — no surprise
// mount semantics, no permission mismatches.

const path = require('path');
const { docker } = require('./docker');
const { WORKDIR } = require('../config');

/**
 * Run `cmd` in the container and capture stdout/stderr. Resolves with
 * `{ stdout, stderr, exitCode }`. `workdir` defaults to the sandbox
 * `/workspace`.
 *
 * We use dockerode's `demuxStream` to split the multiplexed stream back
 * into stdout/stderr chunks. Stdout is collected into a single string
 * for the convenience of the JSON API; the sandbox never produces
 * enough output to make buffering a concern.
 */
async function execIn(container, cmd, { workdir = WORKDIR } = {}) {
  const exec = await container.exec({
    Cmd: ['/bin/sh', '-c', cmd],
    WorkingDir: workdir,
    AttachStdout: true,
    AttachStderr: true,
  });
  const stream = await exec.start({ hijack: true, stdin: false });
  return new Promise((resolve, reject) => {
    let out = '';
    let err = '';
    docker.modem.demuxStream(
      stream,
      { write: (b) => (out += b.toString()) },
      { write: (b) => (err += b.toString()) },
    );
    stream.on('end', async () => {
      try {
        const inspect = await exec.inspect();
        resolve({ stdout: out, stderr: err, exitCode: inspect.ExitCode ?? 0 });
      } catch (e) {
        reject(e);
      }
    });
    stream.on('error', reject);
  });
}

/**
 * Write `contents` (utf8) to `filePath` inside the container. Uses
 * base64 to sidestep shell-quoting headaches and a tmp file + rename
 * so a partial write can't leave a half-finished file behind.
 */
async function writeFile(container, filePath, contents) {
  // Use base64 to avoid shell-quoting hell.
  const b64 = Buffer.from(contents, 'utf8').toString('base64');
  const dir = path.posix.dirname(filePath);
  const file = path.posix.basename(filePath);
  // Write to a tmp file, then move into place after mkdir -p.
  const tmp = `/tmp/.replit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const cmd = [
    `mkdir -p '${dir}'`,
    `printf '%s' '${b64}' | base64 -d > '${tmp}'`,
    `mv '${tmp}' '${filePath}'`,
  ].join(' && ');
  return execIn(container, cmd);
}

/**
 * Read the contents of `filePath`. Throws `{ code: 'ENOENT' }` if the
 * file doesn't exist so the route layer can map it to a 404.
 */
async function readFile(container, filePath) {
  const { stdout, stderr, exitCode } = await execIn(
    container,
    `cat '${filePath}' 2>/dev/null || echo '__REPLIT_MISSING__'`,
  );
  if (exitCode !== 0 || stdout.includes('__REPLIT_MISSING__')) {
    const err = new Error(`File not found: ${filePath}`);
    err.code = 'ENOENT';
    throw err;
  }
  return stdout;
}

/**
 * List the immediate children of `dir`. We deliberately return only one
 * level — the frontend renders a lazy-explorer tree (each row fetches
 * its own children on expand), so dumping every descendant at once
 * flattens the UI and produces duplicate rows when a child re-fetches
 * its own subtree.
 *
 * `ls -1Ap` lists one entry per line, with `/` appended to directories
 * so we can tell them apart without a separate `stat`. We filter out
 * `node_modules` and `.git` here too — those trees are huge and the
 * editor doesn't need them.
 */
async function listDir(container, dir) {
  const cmd = [
    `cd '${dir}'`,
    `ls -1Ap 2>/dev/null | grep -v -E '(^|/)(node_modules|\\.git)(/|$)' || true`,
  ].join(' && ');
  const { stdout } = await execIn(container, cmd);
  // Strip a trailing slash on `dir` so joining is clean: if the caller
  // asked for `/workspace/` we still want `src` not `/src`.
  const parent = dir.replace(/\/+$/, '') || '/';
  const entries = stdout
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((name) => {
      const isDir = name.endsWith('/');
      const clean = isDir ? name.slice(0, -1) : name;
      // Frontend expects the absolute path under the workspace root
      // (e.g. `src/components/Sidebar.jsx`) because it uses it for
      // api.writeFile / api.deleteFile / recursive api.tree calls.
      const abs = parent === '/' ? `/${clean}` : `${parent}/${clean}`;
      return {
        type: isDir ? 'dir' : 'file',
        path: abs,
        size: 0, // size is unused by the explorer; stat per file would
                 // add a syscall per child for no UI benefit.
      };
    });
  return { root: dir, entries };
}

/**
 * Recursive delete (rm -rf). Used for both files and directories — the
 * route layer already validates that the path lives under `/workspace`.
 */
async function deletePath(container, p) {
  return execIn(container, `rm -rf '${p}'`);
}

module.exports = {
  execIn,
  readFile,
  writeFile,
  listDir,
  deletePath,
};
