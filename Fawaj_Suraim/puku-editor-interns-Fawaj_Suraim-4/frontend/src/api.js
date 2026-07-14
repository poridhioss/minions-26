const KEY = () => localStorage.getItem('apiKey') || '';

const headers = (extra = {}) => ({
  'Content-Type': 'application/json',
  ...(KEY() ? { 'x-api-key': KEY() } : {}),
  ...extra,
});

/**
 * Centralized fetch wrapper.
 *
 *  - Adds the auth + content-type headers.
 *  - Translates a 401 from the backend into a thrown error with
 *    `code: 'unauthorized'` so the UI can show a friendly message.
 *  - Throws an Error with `code: 'http'` + `status` for any other non-2xx.
 *  - Returns parsed JSON for 2xx, or the raw Response for calls that need it.
 */
async function request(path, init = {}) {
  let r;
  try {
    r = await fetch(path, { ...init, headers: headers(init.headers || {}) });
  } catch (e) {
    // fetch() throws TypeError on DNS failure, refused connection, CORS, etc.
    const err = new Error('Server unreachable — is the backend running?');
    err.code = 'server_down';
    err.cause = e;
    throw err;
  }
  if (r.status === 401) {
    const err = new Error('unauthorized');
    err.code = 'unauthorized';
    err.status = 401;
    throw err;
  }
  // 5xx (and any unexpected gateway/proxy error) — treat as "server down"
  // from the user's perspective. The backend may have crashed, the reverse
  // proxy may be down, or the worker may be wedged. The exact cause is
  // less important than telling the user "request couldn't be made" so
  // they can check the backend before retrying.
  if (r.status >= 500) {
    const err = new Error('Server is down — request could not be made.');
    err.code = 'server_down';
    err.status = r.status;
    throw err;
  }
  if (!r.ok) {
    let body = null;
    try { body = await r.json(); } catch { /* ignore parse error */ }
    const err = new Error(body?.error || `request failed: ${r.status}`);
    err.code = 'http';
    err.status = r.status;
    throw err;
  }
  if (r.status === 204) return null;
  return r.json();
}

export const getApiKey = () => KEY();
export const setApiKey = (k) => localStorage.setItem('apiKey', k);

export async function submitJob({ image, command }) {
  return request('/jobs', { method: 'POST', body: JSON.stringify({ image, command }) });
}

export async function getJob(id) {
  try {
    return await request(`/jobs/${id}`);
  } catch (err) {
    if (err.status === 404) return { state: 'unknown' };
    if (err.code === 'unauthorized') throw err;
    throw err;
  }
}

export async function listJobs() {
  const body = await request('/jobs');
  return Array.isArray(body?.jobs) ? body.jobs : [];
}

export async function deleteJob(id) {
  return request(`/jobs/${id}`, { method: 'DELETE' });
}

export async function deleteJobs(ids) {
  return request('/jobs/delete', { method: 'POST', body: JSON.stringify({ ids }) });
}

export async function cancelJob(id) {
  return request(`/jobs/${id}/cancel`, { method: 'POST' });
}

export async function fetchLogs(id) {
  try {
    const body = await request(`/jobs/${id}/logs`);
    return Array.isArray(body?.lines) ? body.lines : [];
  } catch (err) {
    if (err.code === 'unauthorized') return [];
    throw err;
  }
}

export function streamLogs(id, onEvent) {
  // Backend only listens for ws:// (no TLS in dev). Even if the page is over
  // https:// (tunnel/proxy), we want plain ws:// to the backend.
  const url = `ws://${location.host}/?jobId=${id}${KEY() ? `&token=${encodeURIComponent(KEY())}` : ''}`;
  const ws = new WebSocket(url);
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); }
    catch { onEvent({ type: 'raw', data: e.data }); }
  };
  return ws;
}