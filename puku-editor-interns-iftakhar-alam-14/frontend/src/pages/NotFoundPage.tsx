import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="empty-state" style={{ paddingTop: 80 }}>
      <div style={{ fontSize: 48 }}>404</div>
      <h2>Page not found</h2>
      <p className="text-muted">The URL you tried doesn’t match any route.</p>
      <Link to="/"><button>Back to dashboard</button></Link>
    </div>
  )
}
