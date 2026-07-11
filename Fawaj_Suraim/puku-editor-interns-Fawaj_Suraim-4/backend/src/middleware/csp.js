// src/middleware/csp.js
// Allow inline scripts + eval + inline data-URI images (favicon) + WebSocket
// connections from any origin. Suitable only for a local dev tool.
module.exports = function csp(req, res, next) {
  res.setHeader(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "connect-src 'self' ws: wss:",
    ].join('; ')
  );
  next();
};