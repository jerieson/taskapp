import type { ReactNode } from 'react'

import { InboxIcon } from './icons'

interface EmptyStateProps {
  title: string
  description?: ReactNode
  icon?: ReactNode
  /** e.g. a "Create" button. */
  action?: ReactNode
}

export default function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-box border border-dashed border-base-300 px-4 py-10 text-center">
      <div className="rounded-full bg-base-200 p-3">{icon ?? <InboxIcon className="size-6" />}</div>
      <h2 className="text-lg font-semibold">{title}</h2>
      {description && <p className="max-w-md text-sm text-base-content/80">{description}</p>}
      {action}
    </div>
  )
}
