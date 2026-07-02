/**
 * Small format helpers used across the UI.
 * Kept dependency-free (no date-fns, no Intl.RelativeTimeFormat complexity)
 * so the bundle stays lean.
 */

/** Format an ISO datetime as a short local string. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** "5 minutes ago" / "just now" / "in 2 days". */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (isNaN(then)) return iso
  const now = Date.now()
  const diffSec = Math.round((now - then) / 1000)

  const abs = Math.abs(diffSec)
  const past = diffSec >= 0

  if (abs < 5) return 'just now'
  if (abs < 60) return past ? `${abs}s ago` : `in ${abs}s`
  if (abs < 3600) {
    const m = Math.round(abs / 60)
    return past ? `${m}m ago` : `in ${m}m`
  }
  if (abs < 86400) {
    const h = Math.round(abs / 3600)
    return past ? `${h}h ago` : `in ${h}h`
  }
  const d = Math.round(abs / 86400)
  return past ? `${d}d ago` : `in ${d}d`
}

/** Trim a number to N significant digits, no trailing zeros. */
export function formatNumber(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined || isNaN(n)) return '—'
  if (!isFinite(n)) return n > 0 ? '∞' : '-∞'
  if (n === 0) return '0'
  return Number(n.toPrecision(digits)).toString()
}

/** Render a key/value dict as a flat array of {key, value} strings. */
export function flattenDict(
  d: Record<string, unknown> | null | undefined
): Array<{ key: string; value: string }> {
  if (!d) return []
  return Object.entries(d).map(([k, v]) => ({
    key: k,
    value: typeof v === 'object' ? JSON.stringify(v) : String(v),
  }))
}

/** Truncate a long string in the middle. */
export function truncate(s: string, max = 60): string {
  if (!s || s.length <= max) return s
  const keep = Math.max(0, Math.floor((max - 1) / 2))
  return s.slice(0, keep) + '…' + s.slice(s.length - keep)
}
