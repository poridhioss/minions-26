import { useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer,
} from 'recharts'

import type { Run } from '../api/types'
import { formatNumber } from '../utils/format'

interface Props {
  runs: Run[]
  metricKey: string
  height?: number
}

/**
 * Multi-line chart of a chosen metric across runs.
 *
 * X-axis = run id (newest on the right, with run_name as a label).
 * Y-axis = metric value.
 * Each run gets its own line.
 */
export default function MetricChart({ runs, metricKey, height = 280 }: Props) {
  // Build a wide-format dataset: [{ step: 0, "run-12": 0.5, "run-13": 0.6 }, ...]
  // We only have the LATEST value per metric per run (the API stores a dict),
  // so the chart is single-point per run. That is honest about what the data is.
  const data = useMemo(() => {
    const rows: Array<Record<string, number | string>> = []
    for (const run of runs) {
      const value = run.metrics?.[metricKey]
      if (typeof value !== 'number') continue
      rows.push({
        runId: run.id,
        name: run.run_name || `run-${run.id}`,
        [run.id]: value,
        _label: run.run_name || `run-${run.id}`,
      })
    }
    // Sort by start_time ascending (oldest first so the line reads left-to-right)
    rows.sort((a, b) => Number(a.runId) - Number(b.runId))
    return rows
  }, [runs, metricKey])

  if (data.length === 0) {
    return (
      <div className="text-muted text-sm" style={{ padding: 'var(--sp-4)' }}>
        No runs have logged <code>{metricKey}</code> yet.
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis
            dataKey="_label"
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            angle={-30}
            textAnchor="end"
            height={60}
          />
          <YAxis
            stroke="#64748b"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            tickFormatter={(v: number) => formatNumber(v, 4)}
          />
          <Tooltip
            contentStyle={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 4,
              fontSize: 12,
            }}
            formatter={(v: number) => formatNumber(v, 6)}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
          {runs
            .filter((r) => typeof r.metrics?.[metricKey] === 'number')
            .map((r, idx) => (
              <Line
                key={r.id}
                type="monotone"
                dataKey={String(r.id)}
                name={r.run_name || `run-${r.id}`}
                stroke={COLORS[idx % COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

const COLORS = [
  '#22d3ee', '#a78bfa', '#34d399', '#fbbf24',
  '#f472b6', '#60a5fa', '#fb7185', '#4ade80',
]
