/*
 * daisyUI skeleton loaders, shaped like the content they stand in for so the page
 * does not jump when data arrives. Each top-level loader is one `role="status"`
 * region with a screen-reader label; the shapes themselves are aria-hidden.
 */
import type { ReactNode } from 'react'

import Brand from './Brand'

const WIDTHS = ['w-3/4', 'w-1/2', 'w-2/3', 'w-5/12', 'w-7/12']

function width(i: number): string {
  return WIDTHS[i % WIDTHS.length] ?? 'w-1/2'
}

/** Wraps skeleton shapes in a live region announced as "Loading…". */
function Loading({
  label = 'Loading…',
  className,
  children,
}: {
  label?: string
  className?: string
  children: ReactNode
}) {
  return (
    <div role="status" className={className}>
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="contents">
        {children}
      </div>
    </div>
  )
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <Loading className="flex flex-col gap-2">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className={`skeleton h-4 ${i === 0 ? 'w-full' : width(i)}`} />
      ))}
    </Loading>
  )
}

/** A card with a title and a few lines (generic widget). */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <Loading className="card card-border border-base-300 bg-base-100">
      <div className="card-body gap-3">
        <div className="skeleton h-5 w-1/2" />
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className={`skeleton h-4 ${i === 0 ? 'w-full' : width(i)}`} />
        ))}
      </div>
    </Loading>
  )
}

/**
 * Matches DataTable: a table with a header row from md up, stacked cards below md.
 * The last column is drawn as action buttons when `hasActions` is set.
 */
export function SkeletonTable({
  columns = 4,
  rows = 5,
  hasActions = true,
}: {
  columns?: number
  rows?: number
  hasActions?: boolean
}) {
  const dataColumns = Math.max(1, hasActions ? columns - 1 : columns)
  return (
    <Loading>
      <div className="hidden overflow-hidden rounded-box border border-base-300 bg-base-100 md:block">
        <div className="flex items-center gap-6 border-b border-base-300 px-4 py-3">
          {Array.from({ length: dataColumns }, (_, c) => (
            <div key={c} className="flex-1">
              <div className="skeleton h-3 w-16" />
            </div>
          ))}
          {hasActions && <div className="skeleton ml-auto h-3 w-14" />}
        </div>
        {Array.from({ length: rows }, (_, r) => (
          <div
            key={r}
            className="flex items-center gap-6 border-b border-base-300 px-4 py-4 last:border-b-0"
          >
            {Array.from({ length: dataColumns }, (_, c) => (
              <div key={c} className="flex-1">
                <div className={`skeleton h-4 ${c === 0 ? width(r) : width(r + c + 1)}`} />
              </div>
            ))}
            {hasActions && (
              <div className="ml-auto flex gap-2">
                <div className="skeleton h-8 w-20" />
                <div className="skeleton h-8 w-20" />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 md:hidden">
        {Array.from({ length: Math.min(rows, 3) }, (_, r) => (
          <div key={r} className="card card-border border-base-300 bg-base-100">
            <div className="card-body gap-3 p-4">
              <div className={`skeleton h-5 ${width(r)}`} />
              {Array.from({ length: Math.min(dataColumns - 1, 3) }, (_, c) => (
                <div key={c} className="flex justify-between gap-3">
                  <div className="skeleton h-4 w-20" />
                  <div className={`skeleton h-4 ${c % 2 ? 'w-16' : 'w-24'}`} />
                </div>
              ))}
              {hasActions && (
                <div className="flex gap-2 pt-1">
                  <div className="skeleton h-9 w-24" />
                  <div className="skeleton h-9 w-24" />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Loading>
  )
}

/** A single number tile (dashboards). */
export function SkeletonStat() {
  return (
    <Loading className="card card-border border-base-300 bg-base-100">
      <div className="card-body gap-3 p-4">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton h-8 w-16" />
        <div className="skeleton h-3 w-32" />
      </div>
    </Loading>
  )
}

const BAR_HEIGHTS = ['h-1/3', 'h-2/3', 'h-1/2', 'h-5/6', 'h-2/5', 'h-3/4', 'h-1/2']

/** A chart card: title, bars, axis. */
export function SkeletonChart({ height = 'h-56' }: { height?: string }) {
  return (
    <Loading label="Loading chart…" className="card card-border border-base-300 bg-base-100">
      <div className="card-body gap-4 p-4">
        <div className="skeleton h-5 w-40" />
        <div className={`flex items-end gap-3 border-b border-base-300 pb-1 ${height}`}>
          {BAR_HEIGHTS.map((h, i) => (
            <div key={i} className={`skeleton flex-1 rounded-b-none ${h}`} />
          ))}
        </div>
        <div className="flex justify-between">
          {BAR_HEIGHTS.map((_, i) => (
            <div key={i} className="skeleton h-3 w-6" />
          ))}
        </div>
      </div>
    </Loading>
  )
}

/** Labelled fields and a submit button (forms whose options are loading). */
export function SkeletonForm({ fields = 3 }: { fields?: number }) {
  return (
    <Loading className="flex flex-col gap-4">
      {Array.from({ length: fields }, (_, i) => (
        <div key={i} className="flex flex-col gap-2">
          <div className="skeleton h-3 w-24" />
          <div className="skeleton h-10 w-full" />
        </div>
      ))}
      <div className="skeleton ml-auto h-10 w-28" />
    </Loading>
  )
}

/** Page header plus a table: shown while a route's code loads. */
export function SkeletonPage() {
  return (
    <>
      <div className="mb-6 flex flex-col gap-2" aria-hidden="true">
        <div className="skeleton h-8 w-48" />
        <div className="skeleton h-4 w-72 max-w-full" />
      </div>
      <SkeletonTable />
    </>
  )
}

/** Before the app knows who is logged in. */
export function FullPageSpinner() {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-6 bg-base-100 text-base-content"
      role="status"
    >
      <Brand />
      <span className="loading loading-dots loading-lg text-primary" aria-hidden="true" />
      <span className="sr-only">Loading Taskapp…</span>
    </div>
  )
}
