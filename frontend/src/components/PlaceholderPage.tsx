import EmptyState from './EmptyState'
import { ClockIcon } from './icons'
import PageHeader from './PageHeader'

/** Shared stand-in for screens that later phases build. */
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState
        icon={<ClockIcon className="size-6" />}
        title="Coming soon"
        description={`${title} is not built yet. It will appear here in a later release.`}
      />
    </>
  )
}
