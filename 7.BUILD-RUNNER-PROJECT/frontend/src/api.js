// Thin wrapper around fetch() for talking to the FastAPI backend.
// In dev, Vite proxies /api/* to http://localhost:8000/*
// In prod, we just hit the same origin (FastAPI serves /api/* directly).
const BASE = '/api'

// Optional API key — read from Vite env at build time.
// Set VITE_API_KEY=xxx in frontend/.env or frontend/.env.local.
// If empty, no X-API-Key header is sent (server allows this when API_KEY is unset).
const API_KEY = import.meta.env.VITE_API_KEY || ''

function authHeaders() {
  return API_KEY ? { 'X-API-Key': API_KEY } : {}
}

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    const txt = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${txt}`)
  }
  return res.json()
}

export const api = {
  triggerBuild: (githubUrl) =>
    request(`/build?github_url=${encodeURIComponent(githubUrl)}`, { method: 'POST' }),
  getStatus: (jobId) => request(`/status/${jobId}`),
  getHistory: () => request('/history'),
}

export function openLogSocket(jobId, onMessage) {
  // Use ws:// for dev (proxied) and wss:// for prod, relative to current host.
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/api/logs/${jobId}`
  const ws = new WebSocket(url)
  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)) }
    catch { onMessage({ type: 'log', line: ev.data }) }
  }
  return ws
}
