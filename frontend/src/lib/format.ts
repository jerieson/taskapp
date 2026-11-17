const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** A UTC timestamp from the API, shown as a local date. */
export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso))
}

/** A UTC timestamp from the API, shown as local date and time. */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** A calendar date from the API ("2026-11-17", no time), shown without time zone shifts. */
export function formatDay(isoDate: string): string {
  const [year = 0, month = 1, day = 1] = isoDate.split('-').map(Number)
  return dateFormat.format(new Date(year, month - 1, day))
}

const hoursFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

/** Hours as "1.5 h". */
export function formatHours(hours: number): string {
  return `${hoursFormat.format(hours)} h`
}

/** Today's calendar date in the browser's time zone, as "YYYY-MM-DD". */
export function todayIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const dayWithWeekdayFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

/** A calendar date with its weekday, e.g. "Tue, Nov 17, 2026". */
export function formatDayWithWeekday(isoDate: string): string {
  const [year = 0, month = 1, day = 1] = isoDate.split('-').map(Number)
  return dayWithWeekdayFormat.format(new Date(year, month - 1, day))
}
