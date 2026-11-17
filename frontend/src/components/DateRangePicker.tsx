import { RANGE_PRESETS, type DateRangeState, type RangePreset } from '../lib/dateRange'
import { formatDayRange } from '../lib/format'

/** A preset select, plus start and end dates for a custom range. Use with `useDateRangeParam`. */
export default function DateRangePicker({ state }: { state: DateRangeState }) {
  const { preset, range, setPreset, setCustom } = state
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Date range</span>
        <select
          className="select w-full sm:w-44"
          value={preset}
          onChange={(event) => setPreset(event.target.value as RangePreset)}
        >
          {RANGE_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {preset === 'custom' ? (
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">From</span>
            <input
              type="date"
              className="input w-full sm:w-40"
              value={range.from}
              max={range.to}
              required
              onChange={(event) => {
                if (event.target.value) setCustom({ ...range, from: event.target.value })
              }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">To</span>
            <input
              type="date"
              className="input w-full sm:w-40"
              value={range.to}
              min={range.from}
              required
              onChange={(event) => {
                if (event.target.value) setCustom({ ...range, to: event.target.value })
              }}
            />
          </label>
        </div>
      ) : (
        <p className="text-sm text-base-content/80 sm:pb-2.5" aria-live="polite">
          {formatDayRange(range.from, range.to)}
        </p>
      )}
    </div>
  )
}
