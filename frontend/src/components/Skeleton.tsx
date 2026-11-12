// daisyUI skeleton loaders for lists and widgets.

const WIDTHS = ['w-full', 'w-11/12', 'w-4/5', 'w-2/3', 'w-3/4']

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className={`skeleton h-4 ${WIDTHS[i % WIDTHS.length]}`} />
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className="card bg-base-100 card-border border-base-300" aria-hidden="true">
      <div className="card-body gap-3">
        <div className="skeleton h-5 w-1/2" />
        <SkeletonText lines={3} />
      </div>
    </div>
  )
}

/** Placeholder rows for a table (md and up) or stacked cards (mobile). */
export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton h-12 w-full" />
      ))}
    </div>
  )
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base-100" role="status">
      <span className="loading loading-spinner loading-lg" aria-label="Loading" />
    </div>
  )
}
