/*
 * "Describe your work": free text -> AI draft rows (one or many, e.g. "next week Tuesday
 * to Friday, 4 hrs a day" = four planned rows). One row opens the normal log form,
 * pre-filled; several open a review (DraftReview) saved all at once through the bulk
 * endpoint. Fields the AI could not fill are highlighted. Closing saves nothing.
 */
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'

import { LOG_DRAFT_MAX_CHARS, useLogDraft, type LogDraftRow } from '../../api/ai'
import { ApiError } from '../../api/client'
import ErrorAlert from '../../components/ErrorAlert'
import { SparklesIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import LogFormBody from '../logs/LogForm'
import DraftReview from './DraftReview'

export default function AiLogEntry({ className }: { className?: string }) {
  const id = useId()
  const [text, setText] = useState('')
  /** null = no draft open; [] = the AI found nothing to log. */
  const [rows, setRows] = useState<LogDraftRow[] | null>(null)
  const request = useLogDraft()
  const trimmed = text.trim()

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!trimmed || request.isPending) return
    request.mutate(trimmed, { onSuccess: (draft) => setRows(draft.rows) })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit()
  }

  const limitReached = request.error instanceof ApiError && request.error.status === 429
  const close = () => setRows(null)
  const saved = () => {
    setText('')
    request.reset()
  }
  const single = rows?.length === 1 ? rows[0] : undefined

  return (
    <section
      className={`card card-border border-base-300 bg-base-100 ${className ?? ''}`}
      aria-labelledby={`${id}-label`}
    >
      <form className="card-body gap-2 p-4" onSubmit={submit} noValidate>
        <label id={`${id}-label`} htmlFor={`${id}-text`} className="flex items-center gap-2">
          <span className="inline-flex rounded-full bg-accent p-1 text-accent-content">
            <SparklesIcon className="size-4" />
          </span>
          <span className="font-semibold">Describe your work or plan</span>
        </label>
        <textarea
          id={`${id}-text`}
          className="textarea w-full"
          rows={2}
          maxLength={LOG_DRAFT_MAX_CHARS}
          placeholder="e.g. 2h this morning fixing the login bug for Apollo, or: next week Tuesday to Friday, 4 hrs a day on the workforce API"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={`${id}-note`}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p id={`${id}-note`} className="text-sm text-base-content/80">
            Your text is sent to the AI provider to draft log rows. Nothing is saved until you
            confirm.
          </p>
          <button
            type="submit"
            className="btn btn-primary shrink-0"
            disabled={!trimmed || request.isPending}
          >
            {request.isPending ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              <SparklesIcon className="size-4" />
            )}
            {request.isPending ? 'Drafting…' : 'Draft rows'}
          </button>
        </div>
        {request.isError && (
          <ErrorAlert
            error={request.error}
            title={limitReached ? 'Daily AI limit reached' : 'Could not draft the log'}
            onRetry={limitReached ? undefined : () => submit()}
          />
        )}
        {rows?.length === 0 && (
          <div role="status" className="alert alert-warning text-sm">
            <span>
              No log rows found in that text. Say what you worked on (or will work on), when, and
              for how long.
            </span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={close}>
              Dismiss
            </button>
          </div>
        )}
      </form>

      <Modal open={single !== undefined} title="Review AI draft" onClose={close}>
        {single && <LogFormBody log={null} isOwn draft={single} onSaved={saved} onDone={close} />}
      </Modal>
      <Modal
        open={rows !== null && rows.length > 1}
        title={`Review ${rows?.length ?? 0} AI draft rows`}
        wide
        onClose={close}
      >
        {rows && rows.length > 1 && <DraftReview rows={rows} onSaved={saved} onDone={close} />}
      </Modal>
    </section>
  )
}
