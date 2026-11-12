import EmptyState from './EmptyState'
import PageHeader from './PageHeader'

/** Shared stand-in for screens that later phases build. */
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState title="Coming soon" description="This page is not built yet." />
    </>
  )
}
