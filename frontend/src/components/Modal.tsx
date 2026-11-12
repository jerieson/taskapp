import { useEffect, useId, useRef, type ReactNode } from 'react'

import { CloseIcon } from './icons'

interface ModalProps {
  open: boolean
  title: string
  children: ReactNode
  /** Buttons in the modal-action row. Omit to render your own (e.g. inside a form). */
  actions?: ReactNode
  /** Blocks Escape, backdrop and close button (e.g. while a request is pending). */
  locked?: boolean
  onClose: () => void
}

/** daisyUI dialog: bottom sheet on mobile, centered from sm. */
export default function Modal({ open, title, children, actions, locked, onClose }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      // showModal() focuses the first focusable element (the close button); move focus
      // to the first form control instead, as React's autoFocus intended.
      dialog
        .querySelector<HTMLElement>('.modal-box input, .modal-box select, .modal-box textarea')
        ?.focus()
    }
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="modal modal-bottom sm:modal-middle"
      aria-labelledby={titleId}
      // Escape key.
      onCancel={(event) => {
        event.preventDefault()
        if (!locked) onClose()
      }}
    >
      <div className="modal-box">
        <div className="flex items-start justify-between gap-2">
          <h2 id={titleId} className="text-lg font-bold break-words">
            {title}
          </h2>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square -mt-1 -mr-2"
            onClick={onClose}
            disabled={locked}
            aria-label="Close"
          >
            <CloseIcon />
          </button>
        </div>
        {/* Unmount the content while closed so forms reset between openings. */}
        {open && <div className="pt-4">{children}</div>}
        {open && actions && <div className="modal-action">{actions}</div>}
      </div>
      <div className="modal-backdrop">
        <button type="button" onClick={onClose} disabled={locked} tabIndex={-1}>
          close
        </button>
      </div>
    </dialog>
  )
}
