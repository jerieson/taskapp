import { Link } from 'react-router'

import { ChevronLeftIcon } from './icons'

/** "‹ Parent page" link shown above a detail page's header. */
export default function BackLink({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="btn btn-ghost btn-sm mb-2 -ml-3 max-w-full text-base-content/80">
      <ChevronLeftIcon className="size-4 shrink-0" />
      <span className="truncate">{children}</span>
    </Link>
  )
}
