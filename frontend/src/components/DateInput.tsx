/*
 * Date picker: a field-styled button that opens a calendar (DayPicker, styled by
 * daisyUI's `react-day-picker` class) in a popover anchored under it. Values are
 * calendar dates as "YYYY-MM-DD" ("" = none), like the API.
 *
 * The popover uses the native popover API, so it opens in the top layer and is not
 * clipped by modals; it closes on outside click or Escape. Without CSS anchor
 * positioning (older browsers) daisyUI shows it centred over a backdrop instead.
 *
 * Use `DateField` in forms (label, error, hint), or `DateInput` alone with an
 * aria-label. With React Hook Form, wire it through `Controller`.
 */
import { DayPicker, type Matcher } from '@daypicker/react'
import { useId, useRef, useState, type ReactNode, type Ref, type ToggleEvent } from 'react'

import { formatDayWithWeekday, parseDay, todayIso, toIsoDay } from '../lib/format'
import { FieldWrapper } from './FormField'
import { CalendarIcon } from './icons'

export interface DateInputProps {
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  id?: string
  /** Earliest and latest choosable dates ("YYYY-MM-DD"). */
  min?: string
  max?: string
  placeholder?: string
  /** Offer a "Clear" button (for optional dates). */
  clearable?: boolean
  /** Extra classes for the button (e.g. a width, `join-item`). */
  className?: string
  invalid?: boolean
  describedBy?: string
  'aria-label'?: string
  ref?: Ref<HTMLButtonElement>
}

export function DateInput({
  value,
  onChange,
  onBlur,
  id,
  min,
  max,
  placeholder = 'Pick a date',
  clearable = false,
  className,
  invalid,
  describedBy,
  'aria-label': ariaLabel,
  ref,
}: DateInputProps) {
  const uid = useId()
  const popoverId = `date-${uid}`
  const anchor = `--date-${uid.replace(/[^\w-]/g, '')}`
  const popover = useRef<HTMLDivElement>(null)
  const selected = value ? parseDay(value) : undefined
  // The calendar opens on the chosen date, else the earliest allowed one, else today.
  const startMonth = () => selected ?? (min ? parseDay(min) : new Date())
  const [month, setMonth] = useState<Date>(startMonth)

  const disabled: Matcher[] = []
  if (min) disabled.push({ before: parseDay(min) })
  if (max) disabled.push({ after: parseDay(max) })
  const today = todayIso()
  const todayAllowed = (!min || today >= min) && (!max || today <= max)

  function pick(next: string) {
    onChange(next)
    popover.current?.hidePopover()
  }

  function onToggle(event: ToggleEvent<HTMLDivElement>) {
    if (event.newState !== 'open') return
    setMonth(startMonth())
    // Move focus into the calendar so it can be used with the keyboard.
    requestAnimationFrame(() => {
      const root = popover.current
      // In order of preference (one selector list would return the first in the grid).
      const target = [
        '.rdp-selected .rdp-day_button',
        '.rdp-today:not(.rdp-disabled) .rdp-day_button',
        '.rdp-day_button:not(:disabled)',
      ]
        .map((selector) => root?.querySelector<HTMLButtonElement>(selector))
        .find(Boolean)
      target?.focus()
    })
  }

  return (
    <>
      <button
        type="button"
        id={id}
        ref={ref}
        popoverTarget={popoverId}
        aria-haspopup="dialog"
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onBlur={onBlur}
        className={`input w-full cursor-pointer justify-between gap-2 text-left ${
          invalid ? 'input-error' : ''
        } ${className ?? ''}`}
        style={{ anchorName: anchor }}
      >
        <span className={`truncate ${value ? '' : 'text-base-content/60'}`}>
          {value ? formatDayWithWeekday(value) : placeholder}
        </span>
        <CalendarIcon className="size-4 shrink-0 opacity-70" />
      </button>
      <div
        ref={popover}
        id={popoverId}
        popover="auto"
        role="dialog"
        aria-label={ariaLabel ?? 'Choose a date'}
        onToggle={onToggle}
        className="dropdown date-popover rounded-box border border-base-300 bg-base-100 p-2 shadow-lg"
        style={{ positionAnchor: anchor }}
      >
        <DayPicker
          className="react-day-picker"
          mode="single"
          weekStartsOn={1}
          showOutsideDays
          fixedWeeks
          selected={selected}
          onSelect={(day) => {
            if (day) pick(toIsoDay(day))
          }}
          month={month}
          onMonthChange={setMonth}
          disabled={disabled}
        />
        <div className="flex justify-between gap-2 border-t border-base-300 px-1 pt-2">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={!todayAllowed}
            onClick={() => pick(today)}
          >
            Today
          </button>
          {clearable && value && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => pick('')}>
              Clear
            </button>
          )}
        </div>
      </div>
    </>
  )
}

type DateFieldProps = Omit<DateInputProps, 'invalid' | 'describedBy' | 'id'> & {
  label: string
  error?: string
  hint?: ReactNode
  wrapperClassName?: string
}

/** A labelled date picker with error and hint text, like the other form fields. */
export function DateField({ label, error, hint, wrapperClassName, ...props }: DateFieldProps) {
  const id = useId()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <FieldWrapper id={id} label={label} error={error} hint={hint} className={wrapperClassName}>
      <DateInput id={id} invalid={Boolean(error)} describedBy={describedBy} {...props} />
    </FieldWrapper>
  )
}
