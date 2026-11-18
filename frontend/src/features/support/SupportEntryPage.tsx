/*
 * /support/:id: one support entry in full. The author or an admin can edit it and
 * deactivate / activate it.
 */
import { useState } from 'react'
import { useLocation } from 'react-router'

import { useSupportEntry } from '../../api/support'
import AsyncState from '../../components/AsyncState'
import BackLink from '../../components/BackLink'
import { PencilIcon } from '../../components/icons'
import PageHeader from '../../components/PageHeader'
import { SkeletonPage } from '../../components/Skeleton'
import { formatDateTime } from '../../lib/format'
import { isNotFound, useIdParam } from '../../lib/routing'
import NotFoundPage from '../../routes/NotFoundPage'
import SupportFormModal, { type SupportFormState } from './SupportForm'
import { ActiveToggleModal, EntryDetails, InactiveBadge, TypeBadge } from './SupportBits'
import { placeOf } from './supportText'

/** The list URL (with its search and filters) the user came from, if any. */
function useBackTo(): string {
  const state: unknown = useLocation().state
  if (state && typeof state === 'object' && 'back' in state && typeof state.back === 'string') {
    return state.back.startsWith('/support') ? state.back : '/support'
  }
  return '/support'
}

export default function SupportEntryPage() {
  const id = useIdParam()
  if (id === null) return <NotFoundPage />
  return <EntryView id={id} />
}

function EntryView({ id }: { id: number }) {
  const back = useBackTo()
  const entry = useSupportEntry(id)
  const [form, setForm] = useState<SupportFormState>(null)
  const [toggling, setToggling] = useState(false)

  if (isNotFound(entry.error)) return <NotFoundPage />

  return (
    <AsyncState query={entry} skeleton={<SkeletonPage />}>
      {() => {
        const e = entry.data
        if (!e) return null
        const place = placeOf(e)
        const edited = e.updated_by.id !== e.created_by.id || e.updated_at !== e.created_at
        return (
          <>
            <BackLink to={back}>Support</BackLink>
            <PageHeader
              title={e.concern}
              description={
                <span className="flex flex-wrap items-center gap-2">
                  <TypeBadge type={e.type} />
                  {!e.is_active && <InactiveBadge />}
                  {place && <span className="break-words">{place}</span>}
                </span>
              }
              actions={
                e.can_edit && (
                  <>
                    <button type="button" className="btn btn-primary" onClick={() => setForm(e)}>
                      <PencilIcon className="size-4" />
                      Edit
                    </button>
                    <button type="button" className="btn" onClick={() => setToggling(true)}>
                      {e.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </>
                )
              }
            />

            {!e.is_active && (
              <div role="status" className="alert alert-warning mb-4">
                <span>
                  This entry is inactive: it is hidden from the dictionary unless “Show inactive” is
                  on.
                </span>
              </div>
            )}

            <article className="rounded-box border border-base-300 bg-base-100 p-4 sm:p-6">
              <EntryDetails entry={e} />
              <p className="mt-6 border-t border-base-300 pt-3 text-xs text-base-content/80">
                Added by {e.created_by.username} on {formatDateTime(e.created_at)}
                {edited && (
                  <>
                    {' · '}Last edited by {e.updated_by.username} on {formatDateTime(e.updated_at)}
                  </>
                )}
              </p>
            </article>

            <SupportFormModal state={form} onClose={() => setForm(null)} />
            <ActiveToggleModal entry={toggling ? e : null} onClose={() => setToggling(false)} />
          </>
        )
      }}
    </AsyncState>
  )
}
