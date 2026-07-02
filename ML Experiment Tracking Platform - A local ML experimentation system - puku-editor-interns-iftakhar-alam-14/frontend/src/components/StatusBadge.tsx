import type { RunStatus } from '../api/types'

interface Props {
  status: RunStatus | string | null | undefined
}

/** Coloured pill that turns a run status into something scannable. */
export default function StatusBadge({ status }: Props) {
  const s = (status ?? 'UNKNOWN').toUpperCase()
  const cls =
    s === 'FINISHED' ? 'badge badge-success' :
    s === 'RUNNING'  ? 'badge badge-info' :
    s === 'FAILED'   ? 'badge badge-danger' :
                       'badge badge-muted'

  return <span className={cls}>{s}</span>
}
