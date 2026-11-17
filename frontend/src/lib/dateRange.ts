/*
 * Date range presets for dashboards, kept in the URL so a view can be reloaded or
 * shared: `?range=last-30`, or `?from=YYYY-MM-DD&to=YYYY-MM-DD` for a custom range.
 * Other search params (e.g. `week`) are left untouched.
 */
import { useSearchParams } from 'react-router'

import type { DateRange } from '../api/dashboard'
import { mondayOf, monthStartOf, shiftDay, todayIso } from './format'

export type RangePreset = 'this-week' | 'last-7' | 'this-month' | 'last-30' | 'last-90' | 'custom'

export const RANGE_PRESETS: { value: RangePreset; label: string }[] = [
  { value: 'this-week', label: 'This week' },
  { value: 'last-7', label: 'Last 7 days' },
  { value: 'this-month', label: 'This month' },
  { value: 'last-30', label: 'Last 30 days' },
  { value: 'last-90', label: 'Last 90 days' },
  { value: 'custom', label: 'Custom range' },
]

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** The dates a preset covers, ending today. */
export function presetRange(preset: Exclude<RangePreset, 'custom'>, today: string): DateRange {
  switch (preset) {
    case 'this-week':
      return { from: mondayOf(today), to: today }
    case 'last-7':
      return { from: shiftDay(today, -6), to: today }
    case 'this-month':
      return { from: monthStartOf(today), to: today }
    case 'last-30':
      return { from: shiftDay(today, -29), to: today }
    case 'last-90':
      return { from: shiftDay(today, -89), to: today }
  }
}

function isPreset(value: string | null): value is Exclude<RangePreset, 'custom'> {
  return RANGE_PRESETS.some((p) => p.value === value && p.value !== 'custom')
}

export interface DateRangeState {
  preset: RangePreset
  range: DateRange
  setPreset: (preset: RangePreset) => void
  /** Sets a custom range; an end before the start is moved to the start. */
  setCustom: (range: DateRange) => void
}

export function useDateRangeParam(
  defaultPreset: Exclude<RangePreset, 'custom'> = 'this-month',
): DateRangeState {
  const [params, setParams] = useSearchParams()
  const today = todayIso()
  const from = params.get('from')
  const to = params.get('to')
  const rawPreset = params.get('range')

  let preset: RangePreset
  let range: DateRange
  if (from && to && DATE_PATTERN.test(from) && DATE_PATTERN.test(to) && from <= to) {
    preset = 'custom'
    range = { from, to }
  } else {
    preset = isPreset(rawPreset) ? rawPreset : defaultPreset
    range = presetRange(preset, today)
  }

  const update = (apply: (next: URLSearchParams) => void) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('range')
        next.delete('from')
        next.delete('to')
        apply(next)
        return next
      },
      { replace: true },
    )

  return {
    preset,
    range,
    setPreset: (next) =>
      update((p) => {
        if (next === 'custom') {
          // Start the custom range from what is shown now.
          p.set('from', range.from)
          p.set('to', range.to)
        } else if (next !== defaultPreset) {
          p.set('range', next)
        }
      }),
    setCustom: (next) =>
      update((p) => {
        p.set('from', next.from)
        p.set('to', next.to < next.from ? next.from : next.to)
      }),
  }
}
