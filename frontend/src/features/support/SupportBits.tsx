/*
 * Pieces shared by the support list and detail pages: type badge, place breadcrumb,
 * the cause/resolution/query/notes sections, and the (de)activate confirmation.
 */
import { useState, type ReactNode } from 'react'

import { errorMessage } from '../../api/client'
import { useSetSupportEntryActive, type SupportEntry } from '../../api/support'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import { CheckCircleIcon, CopyIcon } from '../../components/icons'
import { useToast } from '../../components/toast-context'

export function TypeBadge({ type }: { type: SupportEntry['type'] }) {
  return (
    <span className="badge h-auto max-w-full gap-1.5 badge-outline py-0.5">
      <ColorDot color={type.color} />
      <span className="break-words">{type.label}</span>
    </span>
  )
}

export function InactiveBadge() {
  return <span className="badge badge-neutral">Inactive</span>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="min-w-0">
      <h3 className="text-xs font-semibold tracking-wide text-base-content/80 uppercase">
        {title}
      </h3>
      <div className="mt-1">{children}</div>
    </section>
  )
}

function Prose({ text }: { text: string }) {
  return <p className="text-sm break-words whitespace-pre-line">{text}</p>
}

/** SQL in a monospace block that scrolls inside itself, with a Copy button. */
export function QueryBlock({ query }: { query: string }) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(query)
      setCopied(true)
      toast.success('Query copied')
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Could not copy. Select the text and copy it instead.')
    }
  }

  return (
    <div className="relative min-w-0">
      <pre className="max-h-96 overflow-auto rounded-box bg-base-200 p-3 pr-24 font-mono text-sm leading-relaxed">
        <code>{query}</code>
      </pre>
      <button
        type="button"
        className="btn absolute top-2 right-2 btn-sm"
        onClick={() => void copy()}
        aria-label="Copy query"
      >
        {copied ? <CheckCircleIcon className="size-4" /> : <CopyIcon className="size-4" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

/** Cause, resolution, query and notes (whichever are filled in). */
export function EntryDetails({ entry }: { entry: SupportEntry }) {
  const empty = !entry.cause && !entry.resolution && !entry.query && !entry.notes
  if (empty) {
    return <p className="text-sm text-base-content/80">No cause, resolution or query yet.</p>
  }
  return (
    <div className="flex flex-col gap-4">
      {entry.cause && (
        <Section title="Cause">
          <Prose text={entry.cause} />
        </Section>
      )}
      {entry.resolution && (
        <Section title="Resolution">
          <Prose text={entry.resolution} />
        </Section>
      )}
      {entry.query && (
        <Section title="Query">
          <QueryBlock query={entry.query} />
        </Section>
      )}
      {entry.notes && (
        <Section title="Notes">
          <Prose text={entry.notes} />
        </Section>
      )}
    </div>
  )
}

/** Confirmation before deactivating (or activating) an entry. */
export function ActiveToggleModal({
  entry,
  onClose,
}: {
  entry: SupportEntry | null
  onClose: () => void
}) {
  const toast = useToast()
  const setActive = useSetSupportEntryActive()
  const activating = entry ? !entry.is_active : false

  function confirm() {
    if (!entry) return
    setActive.mutate(
      { id: entry.id, active: activating },
      {
        onSuccess: () => toast.success(activating ? 'Entry activated' : 'Entry deactivated'),
        onError: (error) => toast.error(errorMessage(error)),
        onSettled: onClose,
      },
    )
  }

  return (
    <ConfirmModal
      open={entry !== null}
      title={activating ? 'Activate entry?' : 'Deactivate entry?'}
      confirmLabel={activating ? 'Activate' : 'Deactivate'}
      tone={activating ? 'primary' : 'error'}
      isPending={setActive.isPending}
      onConfirm={confirm}
      onCancel={onClose}
    >
      <p className="break-words">
        {activating
          ? 'It will show in the support dictionary again.'
          : 'It will be hidden from the support dictionary (shown only with “Show inactive”). You can activate it again later.'}
      </p>
      {entry && <p className="mt-2 font-semibold break-words">{entry.concern}</p>}
    </ConfirmModal>
  )
}
