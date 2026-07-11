class Queue {
     constructor() {}
     async getJob(id) { return id === 'j1' ? global.__stubJob : undefined; }
     async close() {}
   }
   module.exports = { Queue };