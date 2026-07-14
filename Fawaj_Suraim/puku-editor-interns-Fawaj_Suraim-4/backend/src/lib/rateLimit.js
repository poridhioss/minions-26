// Fixed-window per-key rate limiter. In-memory only (each process keeps its
// own counter), so behind a load balancer N replicas multiply the limit by N.
// Good enough for a single-host orchestrator; swap for a Redis-backed
// limiter if you scale horizontally.

function makeLimiter({ windowMs, max, name }) {
  const hits = new Map(); // key -> { count, resetAt }
  function check(key) {
    const now = Date.now();
    const bucket = hits.get(key);
    if (!bucket || bucket.resetAt <= now) {
      hits.set(key, { count: 1, resetAt: now + windowMs });
      return { ok: true, remaining: max - 1, resetAt: now + windowMs };
    }
    bucket.count += 1;
    return {
      ok: bucket.count <= max,
      remaining: Math.max(0, max - bucket.count),
      resetAt: bucket.resetAt,
    };
  }
  // Garbage-collect empty buckets every 5 minutes so a long-running process
  // doesn't grow unbounded under churn (many distinct keys).
  const gc = setInterval(() => {
    const now = Date.now();
    for (const [k, v] of hits) if (v.resetAt <= now) hits.delete(k);
  }, 5 * 60_000);
  gc.unref();
  return {
    name,
    middleware(req, res, next) {
      const key = req.header('x-api-key') || req.ip || 'anon';
      const r = check(key);
      res.setHeader('x-ratelimit-limit', String(max));
      res.setHeader('x-ratelimit-remaining', String(r.remaining));
      res.setHeader('x-ratelimit-reset', String(Math.ceil(r.resetAt / 1000)));
      if (!r.ok) {
        res.setHeader('retry-after', String(Math.ceil((r.resetAt - Date.now()) / 1000)));
        return res.status(429).json({ error: 'rate_limited' });
      }
      next();
    },
  };
}

module.exports = { makeLimiter };