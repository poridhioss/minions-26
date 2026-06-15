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

export default function History({ jobs, onSelect, onRefresh }) {
  return (
    <section className="card">
      <h2>
        Recent Builds
        <button className="ghost" onClick={onRefresh} title="Refresh history">↻ refresh</button>
      </h2>
      {jobs.length === 0 ? (
        <p className="empty">No builds yet — trigger one above ↑</p>
      ) : (
        <div className="history">
          {jobs.map((job) => (
            <div key={job.job_id} className="history-item" onClick={() => onSelect(job)}>
              <div>
                <div className="repo">{repoName(job.github_url)}</div>
                <div className="job">
                  {job.job_id?.split('-')[0]} • {job.status}
                  {job.message && ` • ${job.message.slice(0, 50)}`}
                </div>
              </div>
              <span className={`badge ${STATUS_BADGE[job.status] || 'badge-queued'}`}>
                {job.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
