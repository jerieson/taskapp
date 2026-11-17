import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { HoursPerWeek } from '../../api/dashboard'
import { axisTick, hoveredRow, useChartColors } from '../../lib/chartColors'
import { formatDay, formatHours, formatShortDay, shiftDay } from '../../lib/format'
import { ChartTable, ChartTooltip } from './ChartParts'

interface Row {
  week: string
  label: string
  hours: number
}

const weekTitle = (monday: string) => `Week of ${formatDay(monday)}`

export default function HoursPerWeekChart({ data }: { data: HoursPerWeek }) {
  const colors = useChartColors()
  const rows: Row[] = data.weeks.map((w) => ({
    week: w.week_start,
    label: formatShortDay(w.week_start),
    hours: w.hours,
  }))
  return (
    <>
      <div className="h-56" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke={colors.grid} />
            <XAxis
              dataKey="label"
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={{ stroke: colors.grid }}
              minTickGap={16}
              padding={{ left: 8, right: 8 }}
            />
            <YAxis
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={40}
            />
            <Tooltip
              cursor={{ stroke: colors.grid, strokeWidth: 1 }}
              content={(props) => {
                const row = hoveredRow<Row>(props)
                if (!row) return null
                return (
                  <ChartTooltip
                    title={`${formatShortDay(row.week)} – ${formatShortDay(shiftDay(row.week, 6))}`}
                    value={formatHours(row.hours)}
                  />
                )
              }}
            />
            <Line
              type="monotone"
              dataKey="hours"
              stroke={colors.series}
              strokeWidth={2}
              dot={{ r: 4, fill: colors.series, stroke: colors.surface, strokeWidth: 2 }}
              activeDot={{ r: 6, fill: colors.series, stroke: colors.surface, strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        caption="Hours per week"
        columns={['Week', 'Hours']}
        rows={rows.map((r) => ({
          key: r.week,
          label: weekTitle(r.week),
          value: formatHours(r.hours),
        }))}
      />
    </>
  )
}
