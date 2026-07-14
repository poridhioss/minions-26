// src/lib/logger.js
// Tiny structured logger: timestamp, level, message, plus arbitrary fields.
// JSON-on-stdout so a log shipper (Vector, Fluent Bit) can ingest it later.

function emit(level, msg, fields = {}) {
  const line = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...fields,
  };
  const out = JSON.stringify(line);
  if (level === 'error') process.stderr.write(out + '\n');
  else process.stdout.write(out + '\n');
}

module.exports = {
  info: (msg, fields) => emit('info', msg, fields),
  warn: (msg, fields) => emit('warn', msg, fields),
  error: (msg, fields) => emit('error', msg, fields),
  debug: (msg, fields) => {
    if (process.env.LOG_LEVEL === 'debug') emit('debug', msg, fields);
  },
  // Express-style middleware
  middleware: (req, res, next) => {
    const reqId = req.headers['x-request-id'] || require('uuid').v4();
    req.id = reqId;
    // Per-request logger so downstream middleware (auth, csp, etc.) can
    // emit structured warnings tied to this request without re-stamping the
    // id themselves. Without this, `req.log?.warn?.(...)` calls in those
    // middleware become silent no-ops.
    req.log = {
      info:  (msg, fields = {}) => emit('info',  msg, { reqId, ...fields }),
      warn:  (msg, fields = {}) => emit('warn',  msg, { reqId, ...fields }),
      error: (msg, fields = {}) => emit('error', msg, { reqId, ...fields }),
      debug: (msg, fields = {}) => {
        if (process.env.LOG_LEVEL === 'debug') emit('debug', msg, { reqId, ...fields });
      },
    };
    res.setHeader('x-request-id', reqId);
    const start = process.hrtime.bigint();
    res.on('finish', () => {
      const durMs = Number(process.hrtime.bigint() - start) / 1e6;
      emit('info', 'http_request', {
        reqId,
        method: req.method,
        path: req.path,
        status: res.statusCode,
        durationMs: Math.round(durMs),
        jobId: req.params && req.params.id,
      });
    });
    next();
  },
};
