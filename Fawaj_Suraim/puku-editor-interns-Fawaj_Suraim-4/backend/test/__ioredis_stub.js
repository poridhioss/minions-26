class Redis {
     constructor() {
       global.__stubRedisData = global.__stubRedisData || {};
     }
     async get(_k) { return global.__stubRedisData[_k] ?? null; }
     async set(_k, _v, _mode, _ttl) { global.__stubRedisData[_k] = _v; return 'OK'; }
     async del(_k) { delete global.__stubRedisData[_k]; return 0; }
     on() { return this; }
     async quit() { return 'OK'; }
     disconnect() {}
   }
   module.exports = Redis;
   module.exports.default = Redis;