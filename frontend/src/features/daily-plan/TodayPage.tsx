/*
 * /today: the daily plan for a date (?date=YYYY-MM-DD, default today).
 *
 * An ordered list of the user's own tasks with planned hours, compared against
 * WORKDAY_HOURS. Tasks are added from a searchable picker of open tasks; each item can
 * be moved up/down, have its hours changed, be marked done, or start a prod log.
 */
import { useSearchParams } from 'react-router'
import { useState } from 'react'

import { errorMessage } from '../../api/client'
import {
  usePlan,
  useRemovePlanItem,
  useReorderPlan,
  type Plan,
  type PlanItem,
} from '../../api/plans'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import { CalendarIcon, PlusIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDayWithWeekday, todayIso } from '../../lib/format'
import LogFormBody, { type LogPrefill } from '../logs/LogForm'
import DateNav from './DateNav'
import PlanItemCard from './PlanItemCard'
import PlanSummary from './PlanSummary'
import TaskPicker from './TaskPicker'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

function usePlanDate(): [string, (date: string) => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get('date')
  const date = raw && DATE_PATTERN.test(raw) ? raw : todayIso()
  const setDate = (next: string) =>
    setParams(next === todayIso() ? {} : { date: next }, { replace: true })
  return [date, setDate]
}

function PlanSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <SkeletonCard lines={1} />
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
    </div>
  )
}

export default function TodayPage() {
  const toast = useToast()
  const [planDate, setPlanDate] = usePlanDate()
  const plan = usePlan(planDate)
  const reorder = useReorderPlan(planDate)
  const remove = useRemovePlanItem(planDate)
  const [picking, setPicking] = useState(false)
  const [logging, setLogging] = useState<LogPrefill | null>(null)

  const isToday = planDate === todayIso()
  const items = plan.data?.items ?? []

  function move(current: Plan, index: number, by: -1 | 1) {
    const ids = current.items.map((item) => item.id)
    const target = index + by
    const [moved] = ids.splice(index, 1)
    if (moved === undefined || target < 0 || target > ids.length) return
    ids.splice(target, 0, moved)
    reorder.mutate(
      { planId: current.id, itemIds: ids },
      { onError: (error) => toast.error(errorMessage(error)) },
    )
  }

  function removeItem(current: Plan, item: PlanItem) {
    remove.mutate(
      { planId: current.id, itemId: item.id },
      {
        onSuccess: () => toast.success(`Removed “${item.task.title}” from the plan`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const addButton = (
    <button type="button" className="btn btn-primary" onClick={() => setPicking(true)}>
      <PlusIcon />
      Add tasks
    </button>
  )

  return (
    <>
      <PageHeader
        title={isToday ? 'Today' : formatDayWithWeekday(planDate)}
        description={
          isToday
            ? `${formatDayWithWeekday(planDate)}. Plan what you will work on today.`
            : 'Your plan for this day.'
        }
        actions={addButton}
      />

      <DateNav value={planDate} onChange={setPlanDate} />

      <AsyncState
        query={plan}
        isEmpty={items.length === 0}
        skeleton={<PlanSkeleton />}
        empty={
          <EmptyState
            icon={<CalendarIcon className="size-6" />}
            title={isToday ? 'Nothing planned for today' : 'Nothing planned for this day'}
            description="Pick open tasks to work on and how many hours each should take."
            action={addButton}
          />
        }
      >
        {() => {
          const current = plan.data
          if (!current) return null
          return (
            <>
              <PlanSummary plan={current} />
              <ol className="flex flex-col gap-3" aria-label="Planned tasks">
                {current.items.map((item, index) => (
                  <PlanItemCard
                    key={item.id}
                    item={item}
                    planId={current.id}
                    planDate={planDate}
                    position={index + 1}
                    isFirst={index === 0}
                    isLast={index === current.items.length - 1}
                    isBusy={reorder.isPending || remove.isPending}
                    onMove={(by) => move(current, index, by)}
                    onRemove={() => removeItem(current, item)}
                    onLogWork={() =>
                      setLogging({
                        task: item.task,
                        logDate: planDate,
                        hours: item.suggested_hours,
                      })
                    }
                  />
                ))}
              </ol>
            </>
          )
        }}
      </AsyncState>

      <Modal open={picking} title="Add tasks to the plan" onClose={() => setPicking(false)}>
        {picking && (
          <TaskPicker
            planDate={planDate}
            plan={plan.data ?? null}
            onDone={() => setPicking(false)}
          />
        )}
      </Modal>

      <Modal open={logging !== null} title="Log work" onClose={() => setLogging(null)}>
        {logging && (
          <LogFormBody log={null} isOwn prefill={logging} onDone={() => setLogging(null)} />
        )}
      </Modal>
    </>
  )
}
