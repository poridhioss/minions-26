import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { experimentsApi, runsApi } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { useAsync } from '../hooks/useAsync'
import { formatRelative, truncate } from '../utils/format'
import type { Experiment, Run } from '../api/types'

export default function DashboardPage() {
  const expCount = useAsync(() => experimentsApi.count(), [])
  const runCount = useAsync(() => runsApi.count(), [])
  const recent = useAsync(
    async () => ({ experiments: await experimentsApi.list({ skip: 0, limit: 5 }), runs: await runsApi.list({ skip: 0, limit: 8 }) }),
    [],
  )

  // Ticking clock so "5m ago" updates without re-fetching
  const [, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 60_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <div className="section-header">
        <h1>Dashboard</h1>
        <button className="ghost" onClick={() => { expCount.refresh(); runCount.refresh(); recent.refresh() }}>
          Refresh
        </button>
      </div>

      <div className="grid cols-3">
        <StatCard label="Experiments" value={expCount.data ?? null} loading={expCount.loading} />
        <StatCard label="Runs" value={runCount.data ?? null} loading={runCount.loading} />
        <StatCard label="Recent runs shown" value={recent.data?.runs.length ?? null} loading={recent.loading} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <div className="section-header">
            <h2>Recent experiments</h2>
            <Link to="/experiments" className="text-sm">View all →</Link>
          </div>
          {recent.loading && <Spinner size="lg" />}
          {recent.data && recent.data.experiments.length === 0 && (
            <EmptyState
              title="No experiments yet"
              description="Create one to start tracking runs."
              action={<Link to="/experiments"><button>Go to experiments</button></Link>}
            />
          )}
          {recent.data && recent.data.experiments.length > 0 && (
            <ul className="kv-list">
              {recent.data.experiments.map((e: Experiment) => (
                <li key={e.id} className="kv-row">
                  <Link to={`/experiments/${e.id}`}>{e.name}</Link>
                  <span className="text-muted text-sm">{formatRelative(e.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <div className="section-header">
            <h2>Recent runs</h2>
            <Link to="/experiments" className="text-sm">View all →</Link>
          </div>
          {recent.loading && <Spinner size="lg" />}
          {recent.data && recent.data.runs.length === 0 && (
            <EmptyState title="No runs yet" description="Start a run inside an experiment to see it here." />
          )}
          {recent.data && recent.data.runs.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Experiment</th>
                  <th>Status</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {recent.data.runs.map((r: Run) => (
                  <tr key={r.id}>
                    <td><Link to={`/experiments/${r.experiment_id}/runs/${r.id}`}>{truncate(r.run_name ?? `#${r.id}`, 28)}</Link></td>
                    <td className="mono text-muted">#{r.experiment_id}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="text-muted text-sm">{formatRelative(r.start_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, loading }: { label: string; value: number | null; loading: boolean }) {
  return (
    <div className="card stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {loading ? <Spinner /> : value === null ? '—' : value.toLocaleString()}
      </div>
    </div>
  )
}
