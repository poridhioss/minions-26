// src/lib/safeEqual.js
// Constant-time string comparison.
//
// `===` returns on the first mismatched byte. That timing difference leaks
// the comparison target one byte at a time to anyone who can measure
// response latency — over a network this is enough to brute-force an API
// key character by character.
//
// `crypto.timingSafeEqual` always touches every byte before returning, so
// timing leaks nothing. Use this for any secret comparison: API keys,
// session tokens, password hashes, etc.
const crypto = require('node:crypto');

function safeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

module.exports = safeEqual;