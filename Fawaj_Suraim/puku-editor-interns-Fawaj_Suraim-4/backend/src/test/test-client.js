// test-client.js
const WebSocket = require('ws');
const jobId = process.argv[2];
const ws = new WebSocket(`ws://localhost:3000?jobId=${jobId}`);
ws.on('message', (m) => console.log(m.toString()));