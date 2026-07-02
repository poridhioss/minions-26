import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

import { experimentsApi, runsApi } from '../api/client'
import type { Run } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import ConfirmButton from '../components/ConfirmButton'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import MetricChart from '../components/MetricChart'
import Modal from '../components/Modal'
import { useAsync } from '../hooks/useAsync'
import { formatDateTime, formatRelative, flattenDict } from '../utils/format'

export default function ExperimentDetailPage() {
  const { id } = useParams()
  const expId = Number(id)
  const navigate = useNavigate()

  const exp = useAsync(() => experimentsApi.get(expId), [expId])
  const runs = useAsync(() => runsApi.listForExperiment(expId), [expId])

  const [showCreate, setShowCreate] = useState(false)
  const [metricKey, setMetricKey] = useState<string | null>(null)

  // Pick the first metric that exists across runs as the default chart key
  const allMetricKeys = Array.from(
    new Set((runs.data ?? []).flatMap((r: Run) => Object.keys(r.metrics ?? {}))),
  )
  const chartKey = metricKey ?? allMetricKeys[0] ?? null

  async function delRun(runId: number) {
    await runsApi.delete(runId)
    toast.success(`Run ${runId} deleted`)
    runs.refresh()
  }

  async function delExperiment() {
    await experimentsApi.delete(expId)
    toast.success('Experiment deleted')
    navigate('/experiments')
  }

  if (exp.loading) return <Spinner size="lg" />
  if (exp.error) return <div className="error-banner">Could not load experiment: {exp.error.message}</div>
  if (!exp.data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="section-header">
        <div>
          <div className="text-muted text-sm">Experiment #{exp.data.id}</div>
          <h1 className="mono">{exp.data.name}</h1>
        </div>
        <div className="flex gap-2">
          <Link to="/experiments"><button className="ghost">← All experiments</button></Link>
          <button className="primary" onClick={() => setShowCreate(true)}>+ New run</button>
          <ConfirmButton onConfirm={delExperiment}>Delete experiment</ConfirmButton>
        </div>
      </div>

      <div className="card">
        <div className="grid cols-3">
          <div>
            <div className="text-muted text-sm">Description</div>
            <div>{exp.data.description || <em className="text-muted">—</em>}</div>
          </div>
          <div>
            <div className="text-muted text-sm">Tags</div>
            <div className="mono text-muted text-sm">{exp.data.tags || '—'}</div>
          </div>
          <div>
            <div className="text-muted text-sm">Created</div>
            <div>
              {formatDateTime(exp.data.created_at)}{' '}
              <span className="text-muted text-sm">({formatRelative(exp.data.created_at)})</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <h2>Metric chart</h2>
          {allMetricKeys.length > 0 && (
            <select value={chartKey ?? ''} onChange={(e) => setMetricKey(e.target.value)}>
              {allMetricKeys.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          )}
        </div>
        {chartKey
          ? <MetricChart runs={runs.data ?? []} metricKey={chartKey} />
          : <div className="text-muted text-sm">No metrics have been logged by any run yet.</div>}
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="section-header" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>
          <h2>Runs ({runs.data?.length ?? 0})</h2>
        </div>
        {runs.loading && <Spinner size="lg" />}
        {runs.data && runs.data.length === 0 && (
          <EmptyState title="No runs yet" description="Click '+ New run' to start tracking a training run." />
        )}
        {runs.data && runs.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Status</th>
                <th>Started</th>
                <th>Params</th>
                <th>Metrics</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r: Run) => (
                <tr key={r.id}>
                  <td className="text-muted">{r.id}</td>
                  <td>
                    <Link to={`/experiments/${expId}/runs/${r.id}`}>{r.run_name}</Link>
                  </td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="text-muted text-sm">{formatRelative(r.start_time)}</td>
                  <td className="text-muted text-sm">{flattenDict(r.parameters).length} keys</td>
                  <td className="text-muted text-sm">{Object.keys(r.metrics ?? {}).length} keys</td>
                  <td style={{ textAlign: 'right' }}>
                    <ConfirmButton onConfirm={() => delRun(r.id)}>Delete</ConfirmButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <CreateRunModal
          experimentId={expId}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); runs.refresh() }}
        />
      )}
    </div>
  )
}

function CreateRunModal({
  experimentId, onClose, onCreated,
}: { experimentId: number; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    setBusy(true); setErr(null)
    try {
      await runsApi.create({ experiment_id: experimentId, run_name: name || `run-${Date.now()}` })
      toast.success('Run created')
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose} title="New run">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-sm">Run name (optional)</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Leave empty for a timestamp name"
            autoFocus
          />
        </label>
        {err && <div className="error-banner">{err}</div>}
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={busy}>
            {busy ? 'Creating…' : 'Create run'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
