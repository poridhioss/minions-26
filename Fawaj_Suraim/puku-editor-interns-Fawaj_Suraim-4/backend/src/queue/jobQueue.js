// src/queue/jobQueue.js
const { Queue } = require('bullmq');
require('dotenv').config();

const connection = {
  host: new URL(process.env.REDIS_URL).hostname,
  port: Number(new URL(process.env.REDIS_URL).port) || 6379,
};

const jobQueue = new Queue('container-jobs', { connection });

module.exports = { jobQueue, connection };