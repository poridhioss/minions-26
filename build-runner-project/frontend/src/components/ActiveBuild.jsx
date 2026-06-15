import { useEffect, useRef } from 'react'

const STATUS_BADGE = {
  queued: 'badge-queued',
  running: 'badge-running',
  cloning: 'badge-running',
  building: 'badge-running',
  pushing: 'badge-running',
  deploying: 'badge-running',
  success: 'badge-success',
  failed: 'badge-failed',
}

function repoName(url) {
  if (!url) return '(no repo)'
  try { return new URL(url).pathname.replace(/^\//, '').replace(/\.git$/, '') }
  catch { return url }
}

export default function ActiveBuild({ job, logs }) {
  const logBoxRef = useRef(null)

  // auto-scroll log box to bottom when new lines arrive
  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
    }
  }, [logs])

  return (
    <section className="card">
      <h2>
        Active Build
        <span className={`badge ${STATUS_BADGE[job.status] || 'badge-queued'}`}>
          {job.status}
        </span>
      </h2>
      <div className="meta">
        <div><strong>Job:</strong> <code>{job.job_id?.split('-')[0]}</code></div>
        <div><strong>Repo:</strong> <code>{repoName(job.github_url)}</code></div>
        <div><strong>Message:</strong> <span>{job.message || '—'}</span></div>
        {job.image_tag && <div><strong>Image:</strong> <code>{job.image_tag}</code></div>}
      </div>
      <h3>Live Logs</h3>
      <pre className="logs" ref={logBoxRef}>
        {logs.length === 0 ? (
          <span className="empty">Waiting for log output…</span>
        ) : (
          logs.map((l, i) => (
            <span key={i} className={`line ${l.level}`}>{l.line}{'\n'}</span>
          ))
        )}
      </pre>
    </section>
  )
}
