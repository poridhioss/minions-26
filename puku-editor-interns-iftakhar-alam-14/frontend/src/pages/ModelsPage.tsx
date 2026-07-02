import { useState } from 'react'

import { modelsApi } from '../api/client'
import Spinner from '../components/Spinner'
import EmptyState from '../components/EmptyState'
import { useAsync } from '../hooks/useAsync'
import { formatRelative } from '../utils/format'
import type { RegisteredModel, RegisteredModelVersion } from '../api/types'

export default function ModelsPage() {
  const list = useAsync(() => modelsApi.list(), [])
  const [selected, setSelected] = useState<string | null>(null)

  if (list.loading) return <Spinner size="lg" />
  if (list.error) return <div className="error-banner">{list.error.message}</div>

  const models = list.data ?? []
  const active = selected ?? models[0]?.name ?? null

  return (
    <div className="flex flex-col gap-4">
      <div className="section-header">
        <h1>Registered models</h1>
        <button className="ghost" onClick={list.refresh}>Refresh</button>
      </div>

      {models.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No registered models"
            description="Promote a run to the registry from the API to see it here."
          />
        </div>
      ) : (
        <div className="grid cols-2">
          <div className="card" style={{ padding: 0 }}>
            <div className="section-header" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>
              <h2>Models ({models.length})</h2>
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {models.map((m: RegisteredModel) => (
                <li
                  key={m.name}
                  onClick={() => setSelected(m.name)}
                  style={{
                    padding: 'var(--sp-3) var(--sp-4)',
                    borderTop: '1px solid var(--border)',
                    cursor: 'pointer',
                    background: active === m.name ? 'var(--bg-1)' : undefined,
                  }}
                >
                  <div className="mono">{m.name}</div>
                  <div className="text-muted text-sm">{m.description || 'No description'}</div>
                  <div className="text-muted text-sm mt-1">
                    {m.latest_versions?.length ?? 0} versions · updated{' '}
                    {formatRelative(m.last_updated ?? m.last_updated_timestamp)}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <VersionsPanel modelName={active} />
        </div>
      )}
    </div>
  )
}

function VersionsPanel({ modelName }: { modelName: string | null }) {
  const v = useAsync(
    () => modelName ? modelsApi.versions(modelName) : Promise.resolve([] as RegisteredModelVersion[]),
    [modelName],
  )

  if (!modelName) return <div className="card"><EmptyState title="Select a model" /></div>
  if (v.loading) return <div className="card"><Spinner size="lg" /></div>
  if (v.error) return <div className="card error-banner">{v.error.message}</div>

  const versions = v.data ?? []

  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="section-header" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>
        <h2 className="mono">{modelName}</h2>
        <button className="ghost" onClick={v.refresh}>Refresh</button>
      </div>
      {versions.length === 0 ? (
        <EmptyState title="No versions yet" />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Stage</th>
              <th>Run</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((ver: RegisteredModelVersion) => (
              <tr key={ver.version}>
                <td className="mono">v{ver.version}</td>
                <td>
                  <span className={`badge ${stageClass(ver.stage)}`}>{ver.stage}</span>
                </td>
                <td className="text-muted text-sm mono">{ver.run_id || '—'}</td>
                <td className="text-muted text-sm">
                  {formatRelative(ver.created_at ?? ver.creation_timestamp)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function stageClass(stage: string): string {
  switch (stage) {
    case 'Production': return 'badge-success'
    case 'Staging': return 'badge-info'
    case 'Archived': return 'badge-muted'
    default: return 'badge-muted'
  }
}
