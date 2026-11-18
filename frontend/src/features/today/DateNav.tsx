import { DateInput } from '../../components/DateInput'
import { ChevronLeftIcon, ChevronRightIcon } from '../../components/icons'
import { shiftDay, todayIso } from '../../lib/format'

interface DateNavProps {
  value: string
  onChange: (date: string) => void
}

/** Previous / next day, a date picker, and a jump back to today. */
export default function DateNav({ value, onChange }: DateNavProps) {
  const isToday = value === todayIso()
  return (
    <nav className="mb-4 flex flex-wrap items-center gap-2" aria-label="Choose a day">
      <div className="join">
        <button
          type="button"
          className="btn join-item btn-square"
          onClick={() => onChange(shiftDay(value, -1))}
          aria-label="Previous day"
        >
          <ChevronLeftIcon />
        </button>
        <DateInput
          className="join-item w-48"
          aria-label="Day"
          value={value}
          onChange={(day) => {
            if (day) onChange(day)
          }}
        />
        <button
          type="button"
          className="btn join-item btn-square"
          onClick={() => onChange(shiftDay(value, 1))}
          aria-label="Next day"
        >
          <ChevronRightIcon />
        </button>
      </div>
      {!isToday && (
        <button type="button" className="btn btn-ghost" onClick={() => onChange(todayIso())}>
          Back to today
        </button>
      )}
    </nav>
  )
}
