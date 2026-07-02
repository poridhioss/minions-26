import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

import { runsApi } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import ConfirmButton from '../components/ConfirmButton'
import Spinner from '../components/Spinner'
import Modal from '../components/Modal'
import { useAsync } from '../hooks/useAsync'
import { formatDateTime, flattenDict } from '../utils/format'

export default function RunDetailPage() {
  const { experimentId, runId } = useParams()
  const expId = Number(experimentId)
  const id = Number(runId)
  const navigate = useNavigate()

  const run = useAsync(() => runsApi.get(id), [id])
  const [showMetric, setShowMetric] = useState(false)
  const [showParam, setShowParam] = useState(false)

  async function finish() {
    await runsApi.finish(id, { status: 'FINISHED' })
    toast.success('Run marked FINISHED')
    run.refresh()
  }

  async function fail() {
    await runsApi.finish(id, { status: 'FAILED' })
    toast.success('Run marked FAILED')
    run.refresh()
  }

  async function del() {
    await runsApi.delete(id)
    toast.success('Run deleted')
    navigate(`/experiments/${expId}`)
  }

  if (run.loading) return <Spinner size="lg" />
  if (run.error) return <div className="error-banner">{run.error.message}</div>
  if (!run.data) return null

  const r = run.data
  const params = flattenDict(r.parameters)
  const metrics = flattenDict(r.metrics)

  return (
    <div className="flex flex-col gap-4">
      <div className="section-header">
        <div>
          <div className="text-muted text-sm">
            <Link to={`/experiments/${expId}`}>Experiment #{expId}</Link> / run #{r.id}
          </div>
          <h1 className="mono">{r.run_name}</h1>
          <div className="mt-1"><StatusBadge status={r.status} /></div>
        </div>
        <div className="flex gap-2">
          {r.status === 'RUNNING' && (
            <>
              <button onClick={finish}>Mark finished</button>
              <button className="danger" onClick={fail}>Mark failed</button>
            </>
          )}
          <button onClick={() => setShowMetric(true)} className="primary">+ Log metric</button>
          <button onClick={() => setShowParam(true)}>+ Log parameter</button>
          <ConfirmButton onConfirm={del}>Delete run</ConfirmButton>
        </div>
      </div>

      <div className="grid cols-3">
        <KV label="Run ID" value={`#${r.id}`} />
        <KV label="Started" value={formatDateTime(r.start_time)} />
        <KV label="Ended" value={r.end_time ? formatDateTime(r.end_time) : <em className="text-muted">—</em>} />
        <KV label="Artifact URI" value={r.artifact_uri || <em className="text-muted">—</em>} mono />
        <KV label="Status message" value={r.status_message || <em className="text-muted">—</em>} />
        <KV label="User" value={r.user_id || <em className="text-muted">—</em>} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2 className="mb-3">Parameters ({params.length})</h2>
          {params.length === 0 ? (
            <div className="text-muted text-sm">No parameters logged yet.</div>
          ) : (
            <ul className="kv-list">
              {params.map(({ key, value }) => (
                <li key={key} className="kv-row mono">
                  <span className="text-muted">{key}</span>
                  <span>{String(value)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h2 className="mb-3">Metrics ({metrics.length})</h2>
          {metrics.length === 0 ? (
            <div className="text-muted text-sm">No metrics logged yet.</div>
          ) : (
            <ul className="kv-list">
              {metrics.map(({ key, value }) => (
                <li key={key} className="kv-row mono">
                  <span className="text-muted">{key}</span>
                  <span>{String(value)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {showMetric && (
        <LogMetricModal
          runId={id}
          onClose={() => setShowMetric(false)}
          onDone={() => { setShowMetric(false); run.refresh() }}
        />
      )}
      {showParam && (
        <LogParamModal
          runId={id}
          onClose={() => setShowParam(false)}
          onDone={() => { setShowParam(false); run.refresh() }}
        />
      )}
    </div>
  )
}

function KV({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="card stat-card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${mono ? 'mono' : ''}`} style={{ fontSize: 14, fontWeight: 400 }}>
        {value}
      </div>
    </div>
  )
}

function LogMetricModal({ runId, onClose, onDone }: { runId: number; onClose: () => void; onDone: () => void }) {
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [step, setStep] = useState('0')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    setBusy(true); setErr(null)
    try {
      await runsApi.logMetric(runId, { key, value: Number(value), step: Number(step) })
      toast.success(`Logged ${key}=${value}`)
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose} title="Log a metric">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-sm">Key</span>
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="loss" autoFocus />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm">Value</span>
          <input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} placeholder="0.142" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm">Step</span>
          <input type="number" step="1" value={step} onChange={(e) => setStep(e.target.value)} />
        </label>
        {err && <div className="error-banner">{err}</div>}
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={!key || value === '' || busy}>
            {busy ? 'Logging…' : 'Log metric'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function LogParamModal({ runId, onClose, onDone }: { runId: number; onClose: () => void; onDone: () => void }) {
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    setBusy(true); setErr(null)
    try {
      await runsApi.logParameter(runId, { key, value })
      toast.success(`Logged ${key}=${value}`)
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose} title="Log a parameter">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-sm">Key</span>
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="lr" autoFocus />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm">Value</span>
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="0.001" />
        </label>
        {err && <div className="error-banner">{err}</div>}
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={!key || value === '' || busy}>
            {busy ? 'Logging…' : 'Log parameter'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
