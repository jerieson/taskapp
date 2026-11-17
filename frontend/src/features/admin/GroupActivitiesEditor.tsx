import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { useLookups, useSetGroupActivities, type ActivityGroup } from '../../api/lookups'
import AsyncState from '../../components/AsyncState'
import { SelectField } from '../../components/FormField'
import { ArrowDownIcon, ArrowUpIcon, CloseIcon, PlusIcon } from '../../components/icons'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'

/**
 * Pick and order an activity group's activities. Inactive members can stay but new
 * ones must be active (the API enforces the same rule).
 */
export default function GroupActivitiesEditor({
  group,
  onDone,
}: {
  group: ActivityGroup
  onDone: () => void
}) {
  const toast = useToast()
  const activities = useLookups('activities', true)
  const save = useSetGroupActivities()
  const [ids, setIds] = useState<number[]>(group.activity_ids)
  const [adding, setAdding] = useState('')

  const byId = new Map((activities.data ?? []).map((activity) => [activity.id, activity]))
  const available = (activities.data ?? []).filter(
    (activity) => activity.is_active && !ids.includes(activity.id),
  )

  function move(index: number, delta: -1 | 1) {
    const next = [...ids]
    const target = index + delta
    const [moved] = next.splice(index, 1)
    if (moved === undefined || target < 0 || target > next.length) return
    next.splice(target, 0, moved)
    setIds(next)
  }

  function add() {
    const id = Number(adding)
    if (!id || ids.includes(id)) return
    setIds([...ids, id])
    setAdding('')
  }

  function submit() {
    save.mutate(
      { id: group.id, activityIds: ids },
      {
        onSuccess: () => {
          toast.success(`Saved the activities of “${group.label}”`)
          onDone()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <AsyncState query={activities} skeleton={<SkeletonForm fields={3} />}>
      {() => (
        <>
          <div className="flex items-end gap-2">
            <SelectField
              label="Add an activity"
              wrapperClassName="min-w-0 flex-1"
              value={adding}
              onChange={(event) => setAdding(event.target.value)}
              disabled={available.length === 0}
            >
              <option value="">
                {available.length === 0 ? 'Every active activity is listed' : 'Choose an activity'}
              </option>
              {available.map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.label}
                </option>
              ))}
            </SelectField>
            <button
              type="button"
              className="btn btn-square mb-1"
              onClick={add}
              disabled={!adding}
              aria-label="Add the chosen activity"
            >
              <PlusIcon />
            </button>
          </div>

          <p className="mt-4 mb-2 text-sm text-base-content/80">
            {ids.length === 1 ? '1 activity' : `${ids.length} activities`}, in the order the log
            form offers them.
          </p>
          {ids.length === 0 ? (
            <p className="rounded-box border border-dashed border-base-300 p-4 text-center text-sm">
              No activities yet. Projects using this group offer nothing to log.
            </p>
          ) : (
            <ul className="list max-h-[50vh] overflow-y-auto rounded-box border border-base-300">
              {ids.map((id, index) => {
                const activity = byId.get(id)
                const label = activity?.label ?? `Activity ${id}`
                return (
                  <li key={id} className="list-row items-center gap-2 py-1 pr-1">
                    <span className="list-col-grow min-w-0 break-words">
                      {label}
                      {activity && !activity.is_active && (
                        <span className="badge badge-sm badge-neutral ml-2">Inactive</span>
                      )}
                    </span>
                    <span className="join">
                      <button
                        type="button"
                        className="btn btn-sm btn-square btn-ghost join-item"
                        onClick={() => move(index, -1)}
                        disabled={index === 0}
                        aria-label={`Move “${label}” up`}
                      >
                        <ArrowUpIcon className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-square btn-ghost join-item"
                        onClick={() => move(index, 1)}
                        disabled={index === ids.length - 1}
                        aria-label={`Move “${label}” down`}
                      >
                        <ArrowDownIcon className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-square btn-ghost join-item"
                        onClick={() => setIds(ids.filter((other) => other !== id))}
                        aria-label={`Remove “${label}”`}
                      >
                        <CloseIcon className="size-4" />
                      </button>
                    </span>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="modal-action">
            <button type="button" className="btn btn-ghost" onClick={onDone}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={submit}
              disabled={save.isPending}
            >
              {save.isPending && <span className="loading loading-spinner loading-sm" />}
              Save
            </button>
          </div>
        </>
      )}
    </AsyncState>
  )
}
