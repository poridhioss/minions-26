import { useState, useEffect, useRef, useCallback } from 'react'
import { api, openLogSocket } from './api'
import BuildForm from './components/BuildForm'
import ActiveBuild from './components/ActiveBuild'
import History from './components/History'

export default function App() {
  const [activeJob, setActiveJob] = useState(null)   // {job_id, status, message, github_url, image_tag?}
  const [logs, setLogs] = useState([])               // [{line, level}]
  const [history, setHistory] = useState([])
  const wsRef = useRef(null)

  const refreshHistory = useCallback(async () => {
    try {
      const data = await api.getHistory()
      setHistory(data.jobs || [])
    } catch (err) {
      console.error('history failed:', err)
    }
  }, [])

  // initial load + poll every 5s
  useEffect(() => { refreshHistory() }, [refreshHistory])
  useEffect(() => {
    const t = setInterval(refreshHistory, 5000)
    return () => clearInterval(t)
  }, [refreshHistory])

  // cleanup websocket on unmount
  useEffect(() => () => wsRef.current?.close(), [])

  async function triggerBuild(githubUrl) {
    try {
      const { job_id } = await api.triggerBuild(githubUrl)
      setActiveJob({ job_id, status: 'queued', message: 'Job submitted…', github_url: githubUrl })
      setLogs([])
      subscribeToJob(job_id)
      refreshHistory()
    } catch (err) {
      alert(`Build failed: ${err.message}`)
    }
  }

  function subscribeToJob(jobId) {
    wsRef.current?.close()
    const ws = openLogSocket(jobId, (msg) => {
      if (msg.type === 'status') {
        setActiveJob((prev) => ({ ...(prev || {}), ...msg }))
        if (['success', 'failed'].includes(msg.status)) {
          refreshHistory()
        }
      } else if (msg.type === 'log') {
        setLogs((prev) => [...prev, { line: msg.line, level: classify(msg.line) }])
      }
    })
    wsRef.current = ws
  }

  function resubscribe(job) {
    setActiveJob(job)
    setLogs([])
    subscribeToJob(job.job_id)
  }

  return (
    <div className="app">
      <header>
        <h1>🚀 Build Runner</h1>
        <p className="subtitle">Paste a GitHub repo URL → get a Docker image on ghcr.io</p>
      </header>

      <main>
        <BuildForm onSubmit={triggerBuild} />
        {activeJob && <ActiveBuild job={activeJob} logs={logs} />}
        <History jobs={history} onSelect={resubscribe} onRefresh={refreshHistory} />
      </main>

      <footer><small>Build Runner • React + FastAPI + Redis + Docker</small></footer>
    </div>
  )
}

function classify(line) {
  if (/error|fail|fatal/i.test(line)) return 'err'
  if (/success|✓|✅/i.test(line)) return 'ok'
  return 'info'
}
