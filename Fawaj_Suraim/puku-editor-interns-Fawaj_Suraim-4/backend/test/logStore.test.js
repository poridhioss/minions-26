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
  // Two newlines total (one per appended record)
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

test.after(() => {
  process.chdir(realCwd);
  fs.rmSync(tmp, { recursive: true, force: true });
});
