/*
 * List renderer: a table from md up, stacked cards below md. Handles the loading
 * (skeleton), error and empty states so every list gets them.
 */
import type { ReactNode } from 'react'

import EmptyState from './EmptyState'
import ErrorAlert from './ErrorAlert'
import { SkeletonRows } from './Skeleton'

export interface Column<T> {
  key: string
  header: string
  cell: (row: T) => ReactNode
  /** Extra classes for the table cell (e.g. `text-right`, `w-32`). */
  className?: string
  /** On mobile cards: render as the card title instead of a labelled row. */
  isTitle?: boolean
  /** On mobile cards: render without the header label (e.g. action buttons). */
  hideLabelOnCard?: boolean
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[] | undefined
  rowKey: (row: T) => string | number
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  /** Shown when there are no rows. */
  empty?: ReactNode
  /** Accessible table caption (visually hidden). */
  caption?: string
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading,
  error,
  onRetry,
  empty,
  caption,
}: DataTableProps<T>) {
  if (isLoading) return <SkeletonRows />
  if (error) return <ErrorAlert error={error} onRetry={onRetry} />
  if (!rows || rows.length === 0) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>

  const titleColumn = columns.find((c) => c.isTitle)
  const bodyColumns = columns.filter((c) => !c.isTitle)

  return (
    <>
      <div className="hidden overflow-x-auto rounded-box border border-base-300 bg-base-100 md:block">
        <table className="table">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col" className={column.className}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="hover:bg-base-200">
                {columns.map((column) => (
                  <td key={column.key} className={column.className}>
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="flex flex-col gap-3 md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="card card-border border-base-300 bg-base-100">
            <div className="card-body gap-2 p-4">
              {titleColumn && (
                <div className="card-title text-base break-words">{titleColumn.cell(row)}</div>
              )}
              <dl className="flex flex-col gap-1 text-sm">
                {bodyColumns.map((column) =>
                  column.hideLabelOnCard ? (
                    <div key={column.key} className="pt-1">
                      {column.cell(row)}
                    </div>
                  ) : (
                    <div key={column.key} className="flex justify-between gap-3">
                      <dt className="shrink-0 text-base-content/80">{column.header}</dt>
                      <dd className="min-w-0 text-right break-words">{column.cell(row)}</dd>
                    </div>
                  ),
                )}
              </dl>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}
