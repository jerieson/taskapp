import { useEffect, useId, useRef, type ReactNode } from 'react'

interface ConfirmModalProps {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel?: string
  /** `error` for destructive actions. */
  tone?: 'primary' | 'error'
  isPending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Confirmation dialog shown before destructive actions. */
export default function ConfirmModal({
  open,
  title,
  children,
  confirmLabel = 'Confirm',
  tone = 'error',
  isPending = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="modal modal-bottom sm:modal-middle"
      aria-labelledby={titleId}
      // Escape key or backdrop click.
      onCancel={(event) => {
        event.preventDefault()
        if (!isPending) onCancel()
      }}
    >
      <div className="modal-box">
        <h2 id={titleId} className="text-lg font-bold">
          {title}
        </h2>
        {children && <div className="py-4">{children}</div>}
        <div className="modal-action">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${tone === 'error' ? 'btn-error' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending && <span className="loading loading-spinner loading-sm" />}
            {confirmLabel}
          </button>
        </div>
      </div>
      <div className="modal-backdrop">
        <button type="button" onClick={onCancel} disabled={isPending} aria-label="Close">
          close
        </button>
      </div>
    </dialog>
  )
}
