/*
 * /today: two tabs.
 * - Day (?date=, default today): the day's rows, planned against actual.
 * - Plan week (?tab=plan&week=, default next week): planned rows Monday to Friday,
 *   copy actions and the deadline countdown.
 * The planning reminder shows above both on the Friday before an unplanned week.
 */
import { useSearchParams } from 'react-router'

import PageHeader from '../../components/PageHeader'
import { formatDayWithWeekday, mondayOf, todayIso } from '../../lib/format'
import DayView from './DayView'
import PlanWeekView from './PlanWeekView'
import { PlanReminder } from './PlanningParts'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

type Tab = 'day' | 'plan'

function validDate(raw: string | null): string | undefined {
  return raw && DATE_PATTERN.test(raw) ? raw : undefined
}

export default function TodayPage() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'plan' ? 'plan' : 'day'
  const date = validDate(params.get('date')) ?? todayIso()
  const rawWeek = validDate(params.get('week'))
  const week = rawWeek ? mondayOf(rawWeek) : undefined

  const setDate = (next: string) =>
    setParams(next === todayIso() ? {} : { date: next }, { replace: true })
  const setWeek = (monday: string | undefined) =>
    setParams(monday ? { tab: 'plan', week: monday } : { tab: 'plan' }, { replace: true })
  const setTab = (next: Tab) => setParams(next === 'plan' ? { tab: 'plan' } : {})

  const isToday = date === todayIso()
  const tabs: { value: Tab; label: string }[] = [
    { value: 'day', label: 'Day' },
    { value: 'plan', label: 'Plan week' },
  ]

  return (
    <>
      <PageHeader
        title={tab === 'plan' ? 'Plan week' : isToday ? 'Today' : formatDayWithWeekday(date)}
        description={
          tab === 'plan'
            ? 'Plan your hours for the week ahead. The plan is due on the Friday before.'
            : isToday
              ? `${formatDayWithWeekday(date)}. Fill in your actual hours as the day goes.`
              : 'Planned and actual hours for this day.'
        }
      />

      <PlanReminder className="mb-4" />

      <div role="tablist" aria-label="View" className="tabs tabs-box mb-4 w-fit">
        {tabs.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            className={`tab ${tab === t.value ? 'tab-active' : ''}`}
            onClick={() => setTab(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'plan' ? (
        <PlanWeekView week={week} onWeekChange={setWeek} />
      ) : (
        <DayView date={date} onDateChange={setDate} />
      )}
    </>
  )
}
