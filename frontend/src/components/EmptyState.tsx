/*
 * Empty state for lists, widgets and placeholder pages.
 *
 * `page` (default): a theme-colored illustration with the icon in a badge, for a
 * whole list or screen. `compact`: icon only and less padding, for widgets and charts.
 * Pass the primary action (e.g. "New team") as `action` so the empty state is a
 * starting point rather than a dead end.
 */
import type { ReactNode } from 'react'

import { InboxIcon } from './icons'

interface EmptyStateProps {
  title: string
  description?: ReactNode
  icon?: ReactNode
  /** e.g. a "Create" button. */
  action?: ReactNode
  size?: 'page' | 'compact'
}

/**
 * Stacked cards behind the icon badge. Only daisyUI semantic colors, so it follows
 * the light and dark themes.
 */
function Illustration({ icon }: { icon: ReactNode }) {
  return (
    <div className="relative h-28 w-40" aria-hidden="true">
      <svg viewBox="0 0 160 112" className="absolute inset-0 size-full" fill="none">
        <ellipse cx="80" cy="100" rx="58" ry="8" className="fill-base-300" />
        {/* back card */}
        <rect
          x="34"
          y="14"
          width="92"
          height="70"
          rx="10"
          transform="rotate(-8 80 49)"
          className="fill-base-200 stroke-base-300"
          strokeWidth="2"
        />
        {/* front card */}
        <rect
          x="30"
          y="20"
          width="100"
          height="72"
          rx="10"
          className="fill-base-100 stroke-base-300"
          strokeWidth="2"
        />
        <rect x="44" y="36" width="44" height="6" rx="3" className="fill-base-300" />
        <rect x="44" y="50" width="72" height="6" rx="3" className="fill-base-200" />
        <rect x="44" y="64" width="58" height="6" rx="3" className="fill-base-200" />
        {/* brand accents */}
        <circle cx="136" cy="22" r="5" className="fill-secondary" />
        <circle cx="22" cy="70" r="3.5" className="fill-accent" />
        <path
          d="M142 50v8M138 54h8"
          className="stroke-secondary"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute right-6 bottom-1 flex size-12 items-center justify-center rounded-full bg-primary text-primary-content shadow-md ring-4 ring-base-100">
        {icon}
      </div>
    </div>
  )
}

export default function EmptyState({
  title,
  description,
  icon,
  action,
  size = 'page',
}: EmptyStateProps) {
  const glyph = icon ?? <InboxIcon className="size-6" />

  if (size === 'compact') {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-6 text-center">
        <div className="rounded-full bg-base-200 p-2.5 text-base-content/80" aria-hidden="true">
          {glyph}
        </div>
        <h3 className="font-semibold">{title}</h3>
        {description && <p className="max-w-sm text-sm text-base-content/80">{description}</p>}
        {action && <div className="mt-1">{action}</div>}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3 rounded-box border border-dashed border-base-300 bg-base-100 px-4 py-10 text-center">
      <Illustration icon={glyph} />
      <h2 className="mt-2 text-lg font-semibold">{title}</h2>
      {description && <p className="max-w-md text-sm text-base-content/80">{description}</p>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}
