import { ChevronLeftIcon, ChevronRightIcon } from './icons'

interface PaginationProps {
  /** From the API's paginated response: { total, limit, offset }. */
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}

export default function Pagination({ total, limit, offset, onChange }: PaginationProps) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))
  const first = offset + 1
  const last = Math.min(offset + limit, total)

  return (
    <nav
      className="mt-4 flex flex-col items-center gap-2 sm:flex-row sm:justify-between"
      aria-label="Pagination"
    >
      <p className="text-sm text-base-content/80">
        {first}–{last} of {total}
      </p>
      <div className="join">
        <button
          type="button"
          className="btn join-item"
          disabled={page <= 1}
          onClick={() => onChange(Math.max(0, offset - limit))}
          aria-label="Previous page"
        >
          <ChevronLeftIcon />
        </button>
        <span className="btn join-item pointer-events-none" aria-current="page">
          Page {page} of {pages}
        </span>
        <button
          type="button"
          className="btn join-item"
          disabled={page >= pages}
          onClick={() => onChange(offset + limit)}
          aria-label="Next page"
        >
          <ChevronRightIcon />
        </button>
      </div>
    </nav>
  )
}
