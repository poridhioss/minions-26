import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'

import { experimentsApi } from '../api/client'
import type { Experiment } from '../api/types'
import Modal from '../components/Modal'
import ConfirmButton from '../components/ConfirmButton'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { useAsync } from '../hooks/useAsync'
import { formatRelative, truncate } from '../utils/format'

export default function ExperimentsListPage() {
  const list = useAsync(() => experimentsApi.list(), [])
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState('')

  const filtered = (list.data ?? []).filter((e) =>
    e.name.toLowerCase().includes(filter.toLowerCase()),
  )

  async function refresh() { list.refresh() }
  async function del(id: number) {
    await experimentsApi.delete(id)
    toast.success(`Experiment ${id} deleted`)
    refresh()
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="section-header">
        <h1>Experiments</h1>
        <div className="flex gap-2">
          <button className="ghost" onClick={refresh}>Refresh</button>
          <button className="primary" onClick={() => setShowCreate(true)}>+ New experiment</button>
        </div>
      </div>

      <input
        type="search"
        placeholder="Filter by name…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      <div className="card" style={{ padding: 0 }}>
        {list.loading && <div className="loading-overlay"><Spinner size="lg" /></div>}
        {list.data && filtered.length === 0 && (
          <EmptyState
            title={filter ? 'No matches' : 'No experiments yet'}
            description={filter ? 'Try a different filter.' : 'Click "+ New experiment" to create the first one.'}
          />
        )}
        {filtered.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Tags</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e: Experiment) => (
                <tr key={e.id}>
                  <td>
                    <Link to={`/experiments/${e.id}`} className="mono">{e.name}</Link>
                  </td>
                  <td className="text-muted">{truncate(e.description || '—', 60)}</td>
                  <td className="text-muted text-sm mono">{e.tags || '—'}</td>
                  <td className="text-muted text-sm">{formatRelative(e.created_at)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <ConfirmButton onConfirm={() => del(e.id)}>Delete</ConfirmButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); refresh() }}
        />
      )}
    </div>
  )
}

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    setBusy(true); setErr(null)
    try {
      await experimentsApi.create({ name, description: desc || null, tags: null })
      toast.success(`Created experiment “${name}”`)
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose} title="New experiment">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-sm">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. iris-baseline" autoFocus />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm">Description</span>
          <textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Optional notes…" />
        </label>
        {err && <div className="error-banner">{err}</div>}
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="primary" onClick={submit} disabled={!name || busy}>
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
