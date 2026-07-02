import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { healthApi } from '../api/client'
import { getApiKey } from '../api/client'
import './Layout.css'

interface NavItem {
  to: string
  label: string
  icon: string
  end?: boolean
}

const NAV: NavItem[] = [
  { to: '/',              label: 'Dashboard',  icon: '▣', end: true },
  { to: '/experiments',   label: 'Experiments', icon: '◇' },
  { to: '/models',        label: 'Models',      icon: '◆' },
  { to: '/playground',    label: 'Playground',  icon: '▶' },
  { to: '/settings',      label: 'Settings',    icon: '⚙' },
]

const TITLES: Record<string, string> = {
  '/':              'Dashboard',
  '/experiments':   'Experiments',
  '/models':        'Registered Models',
  '/playground':    'Prediction Playground',
  '/settings':      'Settings',
}

function usePageTitle(): string {
  const { pathname } = useLocation()
  // Match longest prefix in TITLES (so /experiments/42 still shows "Experiments")
  const key = Object.keys(TITLES)
    .filter((k) => k === '/' ? pathname === '/' : pathname.startsWith(k))
    .sort((a, b) => b.length - a.length)[0]
  return (key && TITLES[key]) || 'ML Tracker'
}

function HealthIndicator() {
  const [state, setState] = useState<'checking' | 'online' | 'offline'>('checking')
  const apiKey = getApiKey()

  useEffect(() => {
    let alive = true
    async function ping() {
      try {
        const h = await healthApi.get()
        if (alive) setState(h.status === 'ok' ? 'online' : 'offline')
      } catch {
        if (alive) setState('offline')
      }
    }
    ping()
    const t = setInterval(ping, 15_000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  if (!apiKey) {
    return (
      <div className="flex items-center gap-2" title="Set your API key in Settings">
        <span className="health-dot offline" />
        <span className="health-text">No API key</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2" title={`Backend health: ${state}`}>
      <span className={`health-dot ${state}`} />
      <span className="health-text">
        {state === 'checking' ? 'Checking…' : state === 'online' ? 'Online' : 'Unreachable'}
      </span>
    </div>
  )
}

export default function Layout() {
  const title = usePageTitle()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <div className="brand-name">ML Tracker</div>
            <div className="brand-sub">v0.1.0</div>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="footer">
          <a href="/docs" target="_blank" rel="noreferrer">API docs →</a>
        </div>
      </aside>

      <header className="header">
        <div className="title">{title}</div>
        <div className="right">
          <HealthIndicator />
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
