import { useCallback, useEffect, useState } from 'react'

interface State<T> {
  data: T | null
  error: Error | null
  loading: boolean
}

/**
 * Tiny data-fetching hook.
 *
 * Returns `{ data, error, loading, refresh }`. Refresh forces a re-run
 * (handy for "reload" buttons). The deps array controls when the fetch
 * is re-triggered automatically.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): State<T> & { refresh: () => void } {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    fn()
      .then((data) => { if (alive) setState({ data, error: null, loading: false }) })
      .catch((err) => { if (alive) setState({ data: null, error: err as Error, loading: false }) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { ...state, refresh }
}
