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
