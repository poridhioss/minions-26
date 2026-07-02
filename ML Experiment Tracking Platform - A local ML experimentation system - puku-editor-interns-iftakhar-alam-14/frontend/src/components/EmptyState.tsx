import type { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  action?: ReactNode
  icon?: string
}

/** Friendly placeholder for empty lists. */
export default function EmptyState({ title, description, action, icon = '∅' }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      {description && <div className="empty-desc">{description}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
