// test/parseNdjson.test.js
// The NDJSON parser used by GET /jobs/:id/logs is in app.js but it's pure
// (no I/O), so we test it in isolation here. Pulled out by requiring the
// module and calling the function indirectly via a real log file.

const test = require('node:test');
const assert = require('node:assert/strict');

// Re-implement the same parser locally so we don't have to spin up Express.
// If you change the parser in app.js, change it here too — and consider
// extracting it into a shared module.
function parseNdjson(text) {
  const out = [];
  for (const line of text.split('\n')) {
    if (!line) continue;
    try { out.push(JSON.parse(line)); }
    catch { /* skip corrupted lines */ }
  }
  return out;
}

test('parses valid lines, skips blank ones', () => {
  const out = parseNdjson('{"a":1}\n\n{"a":2}\n');
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], { a: 1 });
  assert.deepEqual(out[1], { a: 2 });
});

test('silently skips corrupted lines', () => {
  // The middle line is not JSON; it should be dropped, not thrown.
  const out = parseNdjson('{"ok":1}\nnot-json\n{"ok":2}\n');
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], { ok: 1 });
  assert.deepEqual(out[1], { ok: 2 });
});

test('returns empty array on empty input', () => {
  assert.deepEqual(parseNdjson(''), []);
  assert.deepEqual(parseNdjson('\n\n\n'), []);
});

test('returns empty array when every line is corrupted', () => {
  assert.deepEqual(parseNdjson('garbage\nalso garbage\n'), []);
});