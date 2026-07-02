import { useState, type ReactNode } from 'react'

interface Props {
  onConfirm: () => void | Promise<void>
  message?: string
  children: ReactNode
  className?: string
  disabled?: boolean
}

/** Two-step "click to confirm" pattern, safer than window.confirm. */
export default function ConfirmButton({
  onConfirm,
  message = 'Are you sure?',
  children,
  className = 'danger',
  disabled,
}: Props) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!armed) {
    return (
      <button
        className={className}
        disabled={disabled}
        onClick={() => setArmed(true)}
      >
        {children}
      </button>
    )
  }

  async function go() {
    setBusy(true)
    try {
      await onConfirm()
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }

  return (
    <span className="flex items-center gap-2">
      <span className="text-sm text-muted">{message}</span>
      <button className="danger" onClick={go} disabled={busy}>
        {busy ? 'Working…' : 'Confirm'}
      </button>
      <button className="ghost" onClick={() => setArmed(false)} disabled={busy}>
        Cancel
      </button>
    </span>
  )
}
