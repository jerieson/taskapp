/*
 * Default loading / error / empty handling for anything backed by a query: lists,
 * widgets, charts. Renders `children` only once there is data to show.
 *
 *   <AsyncState query={stats} isEmpty={stats.data?.length === 0}
 *     skeleton={<SkeletonChart />} empty={<EmptyState size="compact" title="No hours yet" />}>
 *     {() => <HoursChart data={stats.data!} />}
 *   </AsyncState>
 *
 * Defaults: a card skeleton, the error alert with "Try again", and a compact empty state.
 */
import type { ReactNode } from 'react'

import EmptyState from './EmptyState'
import ErrorAlert from './ErrorAlert'
import { SkeletonCard } from './Skeleton'

/** The parts of a TanStack Query result this needs. */
export interface QueryLike {
  isPending: boolean
  error: unknown
  refetch?: () => unknown
}

interface AsyncStateProps {
  query: QueryLike
  /** True when loaded but there is nothing to show. */
  isEmpty?: boolean
  skeleton?: ReactNode
  empty?: ReactNode
  errorTitle?: string
  /** A function, so it is only evaluated once data is available. */
  children: () => ReactNode
}

export default function AsyncState({
  query,
  isEmpty = false,
  skeleton,
  empty,
  errorTitle,
  children,
}: AsyncStateProps) {
  if (query.isPending) return <>{skeleton ?? <SkeletonCard />}</>
  if (query.error) {
    const { refetch } = query
    return (
      <ErrorAlert
        error={query.error}
        title={errorTitle}
        onRetry={refetch ? () => void refetch() : undefined}
      />
    )
  }
  if (isEmpty) return <>{empty ?? <EmptyState size="compact" title="Nothing here yet" />}</>
  return <>{children()}</>
}
