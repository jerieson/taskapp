/*
 * "Export CSV": download one person's logs for a month or a custom range, in the team
 * sheet's column order. On /logs it exports your own logs; on /team/logs the modal
 * also asks which member (the backend limits managers to their team's rows).
 */
import { useState, type FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { useExportLogs, useTeamMembers, type TeamMember } from '../../api/logs'
import { InputField, SelectField, SubmitButton } from '../../components/FormField'
import { DownloadIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import { useToast } from '../../components/toast-context'
import { memberNote } from '../../lib/labels'
import { monthStartOf, shiftDay, todayIso } from '../../lib/format'

type Mode = 'month' | 'range'

const MAX_DAYS = 366
const MONTHS_BACK = 24

const monthFormat = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' })

/** "YYYY-MM" for `offset` months from the month of `isoDate`. */
function addMonths(isoDate: string, offset: number): string {
  const [year = 0, month = 1] = isoDate.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1 + offset, 1))
  return date.toISOString().slice(0, 7)
}

function monthLabel(month: string): string {
  const [year = 0, m = 1] = month.split('-').map(Number)
  return monthFormat.format(new Date(year, m - 1, 1))
}

/** First and last day of a "YYYY-MM" month. */
function monthRange(month: string): { from: string; to: string } {
  const from = `${month}-01`
  return { from, to: shiftDay(`${addMonths(from, 1)}-01`, -1) }
}

function daysBetween(from: string, to: string): number {
  return (Date.parse(to) - Date.parse(from)) / 86_400_000
}

function memberLabel(member: TeamMember): string {
  const note = memberNote(member)
  return note ? `${member.username} (${note})` : member.username
}

interface ExportLogsProps {
  /** Team view: choose a member of this team. Omitted: your own logs. */
  teamId?: number
  /** Member preselected in the team view (e.g. the member filter). */
  memberId?: string
}

export default function ExportLogs({ teamId, memberId }: ExportLogsProps) {
  const [open, setOpen] = useState(false)
  const exporting = useExportLogs()
  return (
    <>
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        <DownloadIcon />
        Export CSV
      </button>
      <Modal
        open={open}
        title={teamId === undefined ? 'Export your logs' : 'Export a member’s logs'}
        locked={exporting.isPending}
        onClose={() => setOpen(false)}
      >
        <ExportForm
          teamId={teamId}
          memberId={memberId}
          exporting={exporting}
          onDone={() => setOpen(false)}
        />
      </Modal>
    </>
  )
}

function ExportForm({
  teamId,
  memberId,
  exporting,
  onDone,
}: ExportLogsProps & {
  exporting: ReturnType<typeof useExportLogs>
  onDone: () => void
}) {
  const toast = useToast()
  const members = useTeamMembers(teamId)
  const today = todayIso()
  const [mode, setMode] = useState<Mode>('month')
  const [month, setMonth] = useState(today.slice(0, 7))
  const [from, setFrom] = useState(monthStartOf(today))
  const [to, setTo] = useState(today)
  const [member, setMember] = useState(memberId ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Next month (plans) back to two years ago.
  const months = Array.from({ length: MONTHS_BACK + 2 }, (_, i) => addMonths(today, 1 - i))

  function validate(range: { from: string; to: string }): Record<string, string> {
    const found: Record<string, string> = {}
    if (teamId !== undefined && !member) found.member = 'Choose a member'
    if (mode === 'range') {
      if (!range.from) found.from = 'Choose a start date'
      if (!range.to) found.to = 'Choose an end date'
      if (range.from && range.to && range.from > range.to)
        found.to = 'Must be on or after the start date'
      else if (range.from && range.to && daysBetween(range.from, range.to) >= MAX_DAYS)
        found.to = `The range can be at most ${MAX_DAYS} days`
    }
    return found
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const range = mode === 'month' ? monthRange(month) : { from, to }
    const found = validate(range)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    exporting.mutate(
      {
        date_from: range.from,
        date_to: range.to,
        user_id: member ? Number(member) : undefined,
      },
      {
        onSuccess: (name) => {
          toast.success(`Downloaded ${name}`)
          onDone()
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <form onSubmit={submit} noValidate>
      <p className="text-sm text-base-content/80">
        A CSV in the productivity sheet’s column order, sorted by date. Opens in Excel or Google
        Sheets.
      </p>

      {teamId !== undefined && (
        <SelectField
          label="Member"
          value={member}
          disabled={members.isPending}
          error={errors.member ?? (members.error ? 'Could not load the members' : undefined)}
          onChange={(event) => setMember(event.target.value)}
        >
          <option value="">Choose a member</option>
          {members.data?.map((m) => (
            <option key={m.id} value={m.id}>
              {memberLabel(m)}
            </option>
          ))}
        </SelectField>
      )}

      <div className="mt-3 join w-full" role="group" aria-label="Period">
        {(
          [
            ['month', 'Month'],
            ['range', 'Custom range'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`btn join-item flex-1 ${mode === value ? 'btn-primary' : ''}`}
            aria-pressed={mode === value}
            onClick={() => setMode(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'month' ? (
        <SelectField label="Month" value={month} onChange={(event) => setMonth(event.target.value)}>
          {months.map((m) => (
            <option key={m} value={m}>
              {monthLabel(m)}
            </option>
          ))}
        </SelectField>
      ) : (
        <div className="grid gap-x-4 sm:grid-cols-2">
          <InputField
            label="From"
            type="date"
            value={from}
            max={to || undefined}
            error={errors.from}
            onChange={(event) => setFrom(event.target.value)}
          />
          <InputField
            label="Until"
            type="date"
            value={to}
            min={from || undefined}
            error={errors.to}
            onChange={(event) => setTo(event.target.value)}
          />
        </div>
      )}

      <div className="modal-action">
        <button type="button" className="btn" onClick={onDone} disabled={exporting.isPending}>
          Cancel
        </button>
        <SubmitButton isPending={exporting.isPending}>
          <DownloadIcon />
          Download
        </SubmitButton>
      </div>
    </form>
  )
}
