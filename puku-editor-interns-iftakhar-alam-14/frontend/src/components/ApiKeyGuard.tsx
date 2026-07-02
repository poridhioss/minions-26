import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getApiKey } from '../api/client'

interface Props {
  children: ReactNode
}

/** Renders children only if an API key is set, otherwise a friendly nudge. */
export default function ApiKeyGuard({ children }: Props) {
  if (getApiKey()) return <>{children}</>

  return (
    <div className="card" style={{ textAlign: 'center', padding: 'var(--sp-7)' }}>
      <h2>Set an API key to continue</h2>
      <p className="text-muted" style={{ maxWidth: 480, margin: '0 auto var(--sp-4)' }}>
        This app authenticates each request with an <code>X-API-Key</code> header.
        The key is configured server-side in <code>.env</code> — pick one of the
        values from <code>API_KEYS</code> and enter it below.
      </p>
      <Link to="/settings" className="primary" style={{
        display: 'inline-block',
        background: 'var(--accent)',
        color: '#001318',
        padding: '8px 16px',
        borderRadius: 'var(--r-sm)',
        fontWeight: 600,
        textDecoration: 'none',
      }}>
        Open Settings →
      </Link>
    </div>
  )
}
