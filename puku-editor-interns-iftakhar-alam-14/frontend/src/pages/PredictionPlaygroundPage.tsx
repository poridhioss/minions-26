import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'

import { modelsApi, predictionsApi } from '../api/client'
import Spinner from '../components/Spinner'
import { useAsync } from '../hooks/useAsync'

export default function PredictionPlaygroundPage() {
  const models = useAsync(() => modelsApi.list(), [])
  const [modelName, setModelName] = useState('')
  const [version, setVersion] = useState('')
  const [stage, setStage] = useState<'Production' | 'Staging' | 'None'>('Production')
  const [featuresText, setFeaturesText] = useState('{\n  "feature_0": 1.0,\n  "feature_1": 2.0\n}')
  const [result, setResult] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [parseErr, setParseErr] = useState<string | null>(null)

  const versions = useAsync(
    () => modelName ? modelsApi.versions(modelName) : Promise.resolve([]),
    [modelName],
  )

  // Auto-pick first model
  useEffect(() => {
    if (!modelName && models.data && models.data.length > 0) {
      setModelName(models.data[0].name)
    }
  }, [models.data, modelName])

  async function run() {
    setParseErr(null)
    let parsed: unknown
    try { parsed = JSON.parse(featuresText) }
    catch (e) { setParseErr(`Invalid JSON: ${(e as Error).message}`); return }

    setBusy(true)
    try {
      const payload = version
        ? { model_name: modelName, version: Number(version), features: parsed as Record<string, unknown> }
        : { model_name: modelName, stage, features: parsed as Record<string, unknown> }
      const res = await predictionsApi.predict(payload)
      setResult(res)
      toast.success('Predicted')
    } catch (e) {
      setResult({ error: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="section-header">
        <h1>Prediction playground</h1>
        <span className="text-muted text-sm">Send a feature payload to any registered model.</span>
      </div>

      <div className="grid cols-2">
        <div className="card flex flex-col gap-3">
          <h2>Input</h2>

          {models.loading ? <Spinner /> : (
            <label className="flex flex-col gap-1">
              <span className="text-sm">Model</span>
              <select
                value={modelName}
                onChange={(e) => { setModelName(e.target.value); setVersion('') }}
              >
                {(models.data ?? []).map((m) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
            </label>
          )}

          <div className="grid cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-sm">Stage</span>
              <select
                value={stage}
                onChange={(e) => {
                  setStage(e.target.value as 'Production' | 'Staging' | 'None')
                  setVersion('')
                }}
              >
                <option value="Production">Production</option>
                <option value="Staging">Staging</option>
                <option value="None">None</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-sm">Or version (overrides stage)</span>
              <select value={version} onChange={(e) => setVersion(e.target.value)}>
                <option value="">— latest of stage —</option>
                {(versions.data ?? []).map((v) => (
                  <option key={v.version} value={v.version}>v{v.version} ({v.stage})</option>
                ))}
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-sm">Features (JSON)</span>
            <textarea
              rows={10}
              value={featuresText}
              onChange={(e) => setFeaturesText(e.target.value)}
              style={{ fontFamily: 'var(--font-mono)' }}
            />
          </label>

          {parseErr && <div className="error-banner">{parseErr}</div>}

          <div>
            <button className="primary" onClick={run} disabled={!modelName || busy}>
              {busy ? 'Predicting…' : 'Predict'}
            </button>
          </div>
        </div>

        <div className="card">
          <h2 className="mb-3">Response</h2>
          {!result && <div className="text-muted text-sm">Run a prediction to see the result here.</div>}
          {result !== null && (
            <pre style={{ maxHeight: 400, overflow: 'auto' }}>{JSON.stringify(result, null, 2)}</pre>
          )}
        </div>
      </div>
    </div>
  )
}
