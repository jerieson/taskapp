import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { axisTick, hoveredRow, useChartColors } from '../../lib/chartColors'
import { formatDayWithWeekday, formatHours, formatWeekday, todayIso } from '../../lib/format'
import { ChartTable, ChartTooltip } from './ChartParts'

interface Day {
  date: string
  hours: number
  /** Personal dashboard only: planned hours drawn beside the actual hours. */
  planned_hours?: number
}

interface Row {
  date: string
  label: string
  hours: number
  planned?: number
}

/** Actual hours per day; with planned hours alongside when the data has them. */
export default function HoursPerDayChart({ data }: { data: { days: Day[] } }) {
  const colors = useChartColors()
  const today = todayIso()
  const withPlanned = data.days.some((d) => d.planned_hours !== undefined)
  const rows: Row[] = data.days.map((d) => ({
    date: d.date,
    label: formatWeekday(d.date),
    hours: d.hours,
    planned: d.planned_hours,
  }))
  return (
    <>
      {withPlanned && (
        <ul className="mb-1 flex gap-4 text-xs text-base-content/80" aria-hidden="true">
          <li className="flex items-center gap-1.5">
            <span
              className="size-2.5 rounded-sm"
              style={{ background: colors.series, opacity: 0.35 }}
            />
            Planned
          </li>
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: colors.series }} />
            Actual
          </li>
        </ul>
      )}
      <div className="h-56" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: -12 }} barGap={2}>
            <CartesianGrid vertical={false} stroke={colors.grid} />
            <XAxis
              dataKey="label"
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={{ stroke: colors.grid }}
              interval={0}
            />
            <YAxis
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={40}
            />
            <Tooltip
              cursor={{ fill: colors.cursor }}
              content={(props) => {
                const row = hoveredRow<Row>(props)
                if (!row) return null
                const title =
                  formatDayWithWeekday(row.date) + (row.date === today ? ' (today)' : '')
                const value =
                  row.planned === undefined
                    ? formatHours(row.hours)
                    : `${formatHours(row.hours)} actual · ${formatHours(row.planned)} planned`
                return <ChartTooltip title={title} value={value} />
              }}
            />
            {withPlanned && (
              <Bar
                dataKey="planned"
                name="Planned"
                fill={colors.series}
                fillOpacity={0.35}
                radius={[4, 4, 0, 0]}
                maxBarSize={24}
              />
            )}
            <Bar
              dataKey="hours"
              name="Actual"
              fill={colors.series}
              radius={[4, 4, 0, 0]}
              maxBarSize={withPlanned ? 24 : 40}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        caption={withPlanned ? 'Actual and planned hours per day' : 'Hours per day'}
        columns={withPlanned ? ['Day', 'Actual hours', 'Planned hours'] : ['Day', 'Hours']}
        rows={rows.map((r) => ({
          key: r.date,
          label: formatDayWithWeekday(r.date),
          value: formatHours(r.hours),
          extra: r.planned === undefined ? undefined : formatHours(r.planned),
        }))}
      />
    </>
  )
}
