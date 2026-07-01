// Thin REST client. Vite dev server proxies /api -> backend on :3001.
const j = async (res) => {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { msg = (await res.json()).error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
};

export const api = {
  health: () => fetch('/api/health').then(j),
  listContainers: () => fetch('/api/containers').then(j),
  createContainer: () => fetch('/api/containers', { method: 'POST' }).then(j),
  destroyContainer: (id) => fetch(`/api/containers/${id}`, { method: 'DELETE' }).then(j),
  tree: (id, dir = '') =>
    fetch(`/api/containers/${id}/tree?path=${encodeURIComponent(dir)}`).then(j),
  readFile: (id, p) =>
    fetch(`/api/containers/${id}/files?path=${encodeURIComponent(p)}`).then(j),
  writeFile: (id, p, content) =>
    fetch(`/api/containers/${id}/files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p, content }),
    }).then(j),
  deleteFile: (id, p) =>
    fetch(`/api/containers/${id}/files?path=${encodeURIComponent(p)}`, { method: 'DELETE' }).then(j),
  exec: (id, command) =>
    fetch(`/api/containers/${id}/exec`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command }),
    }).then(j),
};
