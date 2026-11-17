import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { HoursPerDay } from '../../api/dashboard'
import { axisTick, hoveredRow, useChartColors } from '../../lib/chartColors'
import { formatDayWithWeekday, formatHours, formatWeekday, todayIso } from '../../lib/format'
import { ChartTable, ChartTooltip } from './ChartParts'

interface Row {
  date: string
  label: string
  hours: number
}

export default function HoursPerDayChart({ data }: { data: HoursPerDay }) {
  const colors = useChartColors()
  const today = todayIso()
  const rows: Row[] = data.days.map((d) => ({
    date: d.date,
    label: formatWeekday(d.date),
    hours: d.hours,
  }))
  return (
    <>
      <div className="h-56" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: -12 }}>
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
                return <ChartTooltip title={title} value={formatHours(row.hours)} />
              }}
            />
            <Bar dataKey="hours" fill={colors.series} radius={[4, 4, 0, 0]} maxBarSize={40} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        caption="Hours per day"
        columns={['Day', 'Hours']}
        rows={rows.map((r) => ({
          key: r.date,
          label: formatDayWithWeekday(r.date),
          value: formatHours(r.hours),
        }))}
      />
    </>
  )
}
