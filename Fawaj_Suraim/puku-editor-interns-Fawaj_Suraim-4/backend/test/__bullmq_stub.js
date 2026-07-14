class Queue {
     constructor() {}
     async getJob(id) { return global.__stubJobById?.[id] ?? (id === 'j1' ? global.__stubJob : undefined); }
     async close() {}
   }
   module.exports = { Queue };