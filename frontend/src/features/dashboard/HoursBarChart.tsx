/*
 * Ranked horizontal bars (hours by project or category). One hue: the bar's label
 * names it, so color carries no identity. Beyond MAX_BARS the rest fold into "Other".
 */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { axisTick, hoveredRow, useChartColors } from '../../lib/chartColors'
import { formatHours } from '../../lib/format'
import { ChartTable, ChartTooltip } from './ChartParts'

export interface BarItem {
  key: string
  label: string
  /** Shown in the tooltip, e.g. "inactive". */
  note?: string
  hours: number
}

const MAX_BARS = 8
const BAR_ROW_HEIGHT = 36
const LABEL_CHARS = 14

function fold(items: BarItem[]): BarItem[] {
  if (items.length <= MAX_BARS) return items
  const rest = items.slice(MAX_BARS - 1)
  const hours = rest.reduce((sum, item) => sum + item.hours, 0)
  return [
    ...items.slice(0, MAX_BARS - 1),
    { key: 'other', label: `Other (${rest.length})`, hours: Math.round(hours * 100) / 100 },
  ]
}

const shorten = (label: string) =>
  label.length > LABEL_CHARS ? `${label.slice(0, LABEL_CHARS - 1)}…` : label

export default function HoursBarChart({ items, caption }: { items: BarItem[]; caption: string }) {
  const colors = useChartColors()
  const rows = fold(items)
  return (
    <>
      <div style={{ height: rows.length * BAR_ROW_HEIGHT + 32 }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
            barCategoryGap={8}
          >
            <CartesianGrid horizontal={false} stroke={colors.grid} />
            <XAxis
              type="number"
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={{ stroke: colors.grid }}
              allowDecimals={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              tick={axisTick(colors)}
              tickLine={false}
              axisLine={false}
              tickFormatter={shorten}
              width={104}
            />
            <Tooltip
              cursor={{ fill: colors.cursor }}
              content={(props) => {
                const row = hoveredRow<BarItem>(props)
                if (!row) return null
                const title = row.note ? `${row.label} (${row.note})` : row.label
                return <ChartTooltip title={title} value={formatHours(row.hours)} />
              }}
            />
            <Bar dataKey="hours" fill={colors.series} radius={[0, 4, 4, 0]} maxBarSize={24} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartTable
        caption={caption}
        columns={['Name', 'Hours']}
        rows={items.map((item) => ({
          key: item.key,
          label: item.note ? `${item.label} (${item.note})` : item.label,
          value: formatHours(item.hours),
        }))}
      />
    </>
  )
}
