/*
 * The log form in a modal, for the three ways it opens: a new row (optionally on a
 * given date), editing a row, or copying a row to other days ("Copy").
 */
import type { ProdLog } from '../../api/logs'
import Modal from '../../components/Modal'
import LogFormBody from './LogForm'

export type LogModalState =
  | { kind: 'new'; date?: string; title?: string }
  | { kind: 'edit'; log: ProdLog }
  | { kind: 'copy'; log: ProdLog }

interface LogFormModalProps {
  /** null = closed. */
  state: LogModalState | null
  onClose: () => void
  /** False when an admin edits someone else's log. */
  isOwn?: boolean
}

function modalTitle(state: LogModalState): string {
  if (state.kind === 'edit') return 'Edit log'
  if (state.kind === 'copy') return 'Copy log'
  return state.title ?? 'New log'
}

export default function LogFormModal({ state, onClose, isOwn = true }: LogFormModalProps) {
  return (
    <Modal open={state !== null} title={state ? modalTitle(state) : ''} onClose={onClose}>
      {state && (
        <LogFormBody
          log={state.kind === 'edit' ? state.log : null}
          isOwn={isOwn}
          prefill={state.kind === 'new' && state.date ? { logDate: state.date } : undefined}
          copyFrom={state.kind === 'copy' ? state.log : undefined}
          onDone={onClose}
        />
      )}
    </Modal>
  )
}
