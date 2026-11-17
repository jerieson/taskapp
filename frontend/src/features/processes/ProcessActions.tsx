/*
 * Activate / deactivate / delete buttons for a process, shared by the list and the
 * process page. Delete is offered only while the process has no runs (the API
 * refuses it otherwise); deactivating keeps the process and its runs.
 */
import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { useDeleteProcess, useSetProcessActive, type ProcessListItem } from '../../api/processes'
import ConfirmModal from '../../components/ConfirmModal'
import { TrashIcon } from '../../components/icons'
import { useToast } from '../../components/toast-context'

interface ProcessMenuProps {
  process: ProcessListItem
  /** Called after the process was deleted (e.g. to leave its page). */
  onDeleted?: () => void
}

export function ProcessMenu({ process, onDeleted }: ProcessMenuProps) {
  const toast = useToast()
  const setActive = useSetProcessActive()
  const remove = useDeleteProcess()
  const [confirming, setConfirming] = useState(false)

  function toggleActive() {
    const active = !process.is_active
    setActive.mutate(
      { id: process.id, active },
      {
        onSuccess: (saved) =>
          toast.success(`“${saved.name}” ${active ? 'activated' : 'deactivated'}`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function confirmDelete() {
    remove.mutate(process.id, {
      onSuccess: () => {
        toast.success(`“${process.name}” deleted`)
        setConfirming(false)
        onDeleted?.()
      },
      onError: (error) => {
        toast.error(errorMessage(error))
        setConfirming(false)
      },
    })
  }

  return (
    <>
      <button
        type="button"
        className="btn btn-sm btn-ghost"
        onClick={toggleActive}
        disabled={setActive.isPending}
      >
        {setActive.isPending && <span className="loading loading-spinner loading-xs" />}
        {process.is_active ? 'Deactivate' : 'Activate'}
      </button>
      {process.run_count === 0 && (
        <button
          type="button"
          className="btn btn-sm btn-ghost btn-square"
          onClick={() => setConfirming(true)}
          aria-label={`Delete ${process.name}`}
          title="Delete"
        >
          <TrashIcon className="size-4" />
        </button>
      )}
      <ConfirmModal
        open={confirming}
        title="Delete process?"
        confirmLabel="Delete"
        isPending={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setConfirming(false)}
      >
        <p>
          <strong className="break-words">{process.name}</strong> and its steps will be deleted.
          This cannot be undone.
        </p>
      </ConfirmModal>
    </>
  )
}
