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
