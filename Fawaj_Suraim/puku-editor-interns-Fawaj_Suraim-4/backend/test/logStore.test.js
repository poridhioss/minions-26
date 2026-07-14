// test/logStore.test.js
// Round-trips logStore against a tmp directory so we never touch the
// real logs/ folder.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const realCwd = process.cwd();
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'logstore-'));
process.chdir(tmp);

const logStore = require('../src/services/logStore');

test('append + read round-trip preserves line ordering', async () => {
  const id = 'abc-123';
  await logStore.append(id, JSON.stringify({ type: 'start' }) + '\n');
  await logStore.append(id, JSON.stringify({ type: 'log', data: 'hello\n' }) + '\n');
  const content = await logStore.read(id);
  assert.ok(content.includes('"type":"start"'));
  assert.ok(content.includes('"data":"hello\\n"'));
  assert.equal(content.split('\n').filter(Boolean).length, 2);
});

test('read returns null for unknown job id', async () => {
  const content = await logStore.read('does-not-exist');
  assert.equal(content, null);
});

test('pathFor returns a path under logs/', () => {
  const p = logStore.pathFor('xyz');
  assert.ok(p.endsWith(path.join('logs', 'xyz.log')));
});

// pathFor is the input gate for read/append/remove — anything caller-supplied
// goes through here. Without the SAFE_ID check, ../, slashes, dots, etc.
// resolve outside logs/ via path.join (arbitrary file read/write).
test('pathFor rejects path traversal in jobId', () => {
  for (const bad of ['../etc/passwd', 'a/b', 'foo.log', 'with space', '', 'a;b']) {
    assert.throws(() => logStore.pathFor(bad), /invalid jobId/, `should reject ${JSON.stringify(bad)}`);
  }
});

test('pathFor accepts typical UUIDs and short ids', () => {
  for (const ok of ['abc-123-DEF', 'jobid_42', 'A1b2C3d4']) {
    const p = logStore.pathFor(ok);
    assert.ok(p.endsWith(path.join('logs', `${ok}.log`)));
  }
});

// `remove` is exercised by the cancel/delete API path, so the absence of
// this test meant a regression in `remove` would slip through.
test('remove deletes the file and is idempotent for unknown ids', async () => {
  const id = 'to-remove';
  await logStore.append(id, JSON.stringify({ type: 'start' }) + '\n');
  assert.ok(fs.existsSync(logStore.pathFor(id)));
  await logStore.remove(id);
  assert.ok(!fs.existsSync(logStore.pathFor(id)));
  // Removing a non-existent file should not throw (ENOENT is swallowed).
  await logStore.remove(id);
  await logStore.remove('never-existed');
});

test.after(() => {
  process.chdir(realCwd);
  fs.rmSync(tmp, { recursive: true, force: true });
});