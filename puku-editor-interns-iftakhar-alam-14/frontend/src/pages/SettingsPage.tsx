import { useEffect, useState } from 'react'

import { getApiKey, setApiKey, healthApi } from '../api/client'

export default function SettingsPage() {
  const [draft, setDraft] = useState('')
  const [saved, setSaved] = useState(getApiKey() ?? '')
  const [checking, setChecking] = useState(false)
  const [health, setHealth] = useState<string | null>(null)

  useEffect(() => {
    if (!saved) return
    healthApi.get()
      .then((h) => setHealth(`OK — ${h.app} v${h.version}`))
      .catch((e) => setHealth(`Failed: ${(e as Error).message}`))
  }, [saved])

  function save() {
    if (!draft) return
    setApiKey(draft)
    setSaved(draft)
    setDraft('')
    setHealth(null)
  }

  function clear() {
    setApiKey('')
    setSaved('')
    setHealth(null)
  }

  async function ping() {
    setChecking(true)
    try {
      const h = await healthApi.get()
      setHealth(`OK — ${h.app} v${h.version}`)
    } catch (e) {
      setHealth(`Failed: ${(e as Error).message}`)
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="flex flex-col gap-6" style={{ maxWidth: 640 }}>
      <h1>Settings</h1>

      <div className="card">
        <h2 className="mb-3">API key</h2>
        <p className="text-muted text-sm mb-3">
          The backend expects an <code>X-API-Key</code> header on every request.
          The key is stored in <code>localStorage</code> (never sent to anyone except the API).
        </p>

        <div className="flex flex-col gap-2">
          <label className="text-sm">Current key</label>
          <div className="mono text-muted">{saved || <em>None set</em>}</div>
        </div>

        <div className="mt-4 flex flex-col gap-2">
          <label className="text-sm" htmlFor="key-input">New key</label>
          <input
            id="key-input"
            type="password"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="paste your key…"
            autoComplete="off"
          />
        </div>

        <div className="mt-3 flex gap-2">
          <button className="primary" onClick={save} disabled={!draft}>Save</button>
          <button onClick={ping} disabled={checking || !saved}>{checking ? 'Pinging…' : 'Test /health'}</button>
          <button className="ghost" onClick={clear} disabled={!saved}>Clear</button>
        </div>

        {health && (
          <div className={`mt-3 text-sm ${health.startsWith('OK') ? '' : 'text-danger'}`}>
            {health}
          </div>
        )}
      </div>
    </div>
  )
}
