import { useState } from 'react'

export default function BuildForm({ onSubmit }) {
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!url.trim()) return
    setSubmitting(true)
    try {
      await onSubmit(url.trim())
      setUrl('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card">
      <h2>New Build</h2>
      <form onSubmit={handleSubmit}>
        <label htmlFor="repo-url">GitHub repository URL</label>
        <input
          id="repo-url"
          type="url"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          disabled={submitting}
        />
        <button type="submit" disabled={submitting || !url.trim()}>
          {submitting ? '⏳ Submitting…' : '⚡ Trigger Build'}
        </button>
      </form>
      <p className="hint">
        ⚠️ Repo <strong>must contain a <code>Dockerfile</code></strong> at its root,
        and the app inside must listen on port <code>8080</code>.
        Try <code>iftakhar-323/demo-app</code> for a working example.
        See <a href="/api/requirements" target="_blank" rel="noreferrer">build requirements</a>.
      </p>
    </section>
  )
}
