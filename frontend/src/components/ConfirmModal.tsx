import type { ReactNode } from 'react'

import Modal from './Modal'

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
  return (
    <Modal
      open={open}
      title={title}
      locked={isPending}
      onClose={onCancel}
      actions={
        <>
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
        </>
      }
    >
      {children}
    </Modal>
  )
}
