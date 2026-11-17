/*
 * "Describe what you worked on": free text -> AI draft -> the normal log form,
 * pre-filled, with fields the AI could not fill highlighted. Saving uses the normal
 * create endpoint; closing the form saves nothing.
 */
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'

import { LOG_DRAFT_MAX_CHARS, useLogDraft, type LogDraft } from '../../api/ai'
import { ApiError } from '../../api/client'
import ErrorAlert from '../../components/ErrorAlert'
import { SparklesIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import LogFormBody from '../logs/LogForm'

export default function AiLogEntry({ className }: { className?: string }) {
  const id = useId()
  const [text, setText] = useState('')
  const [draft, setDraft] = useState<LogDraft | null>(null)
  const request = useLogDraft()
  const trimmed = text.trim()

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!trimmed || request.isPending) return
    request.mutate(trimmed, { onSuccess: setDraft })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit()
  }

  const limitReached = request.error instanceof ApiError && request.error.status === 429

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
          <span className="font-semibold">Describe what you worked on</span>
        </label>
        <textarea
          id={`${id}-text`}
          className="textarea w-full"
          rows={2}
          maxLength={LOG_DRAFT_MAX_CHARS}
          placeholder="e.g. 2h this morning fixing the login redirect bug for Apollo"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={`${id}-note`}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p id={`${id}-note`} className="text-sm text-base-content/80">
            Your text is sent to the AI provider to draft a log. Nothing is saved until you confirm.
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
            {request.isPending ? 'Drafting…' : 'Draft log'}
          </button>
        </div>
        {request.isError && (
          <ErrorAlert
            error={request.error}
            title={limitReached ? 'Daily AI limit reached' : 'Could not draft the log'}
            onRetry={limitReached ? undefined : () => submit()}
          />
        )}
      </form>

      <Modal open={draft !== null} title="Review AI draft" onClose={() => setDraft(null)}>
        {draft && (
          <LogFormBody
            log={null}
            isOwn
            draft={draft}
            onSaved={() => {
              setText('')
              request.reset()
            }}
            onDone={() => setDraft(null)}
          />
        )}
      </Modal>
    </section>
  )
}
