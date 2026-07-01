// In-memory shared state. Two maps:
//
//   containers: containerId -> { container, createdAt }
//     Source of truth for "what sandboxes exist right now." Both the
//     HTTP routes and the Socket.IO handlers consult this before
//     issuing docker calls.
//
//   socketContainers: socketId -> Set<containerId>
//     Tracks which containers a given WebSocket session has touched.
//     On `disconnect` the Socket.IO layer iterates this set and, for
//     any container that no other socket is still using, calls
//     destroySandbox() so AutoRemove can reap the container.
//
// Both maps are deliberately per-process. For a multi-instance
// deployment you'd back these with Redis; for the single-node
// "mini Codespaces" target, in-process is enough.

const containers = new Map();
const socketContainers = new Map();

function trackSocketContainer(socketId, containerId) {
  if (!socketContainers.has(socketId)) {
    socketContainers.set(socketId, new Set());
  }
  socketContainers.get(socketId).add(containerId);
}

/**
 * Release the given socket's ownership. Returns the list of container
 * ids that no longer have any live owner — those are safe to destroy.
 */
function releaseSocket(socketId) {
  const owned = socketContainers.get(socketId);
  if (!owned) return [];
  socketContainers.delete(socketId);

  const orphans = [];
  for (const id of owned) {
    let stillUsed = false;
    for (const set of socketContainers.values()) {
      if (set.has(id)) { stillUsed = true; break; }
    }
    if (!stillUsed) orphans.push(id);
  }
  return orphans;
}

function listContainerIds() {
  return Array.from(containers.keys());
}

module.exports = {
  // container registry
  get: (id) => containers.get(id),
  set: (id, entry) => containers.set(id, entry),
  delete: (id) => containers.delete(id),
  has: (id) => containers.has(id),
  keys: () => containers.keys(),

  // socket ↔ container bookkeeping
  trackSocketContainer,
  releaseSocket,

  // helpers
  listContainerIds,
};
