// src/middleware/auth.js
const crypto = require('node:crypto');

// Constant-time comparison so a leaked timing oracle can't be used to
// brute-force the key character by character.
function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

module.exports = function requireApiKey(req, res, next) {
  const expected = process.env.API_KEY;
  // Auth disabled if API_KEY isn't set. Loudly warn — silent-no-auth is a footgun.
  if (!expected) {
    req.log?.warn?.('auth_disabled_no_api_key_env');
    return next();
  }
  if (expected === 'changeme') {
    req.log?.warn?.('auth_using_default_key');
  }
  const provided = req.header('x-api-key');
  if (!provided || !safeEqual(provided, expected)) {
    req.log?.warn?.('auth_rejected', { hasProvided: Boolean(provided) });
    return res.status(401).json({ error: 'unauthorized' });
  }
  next();
};