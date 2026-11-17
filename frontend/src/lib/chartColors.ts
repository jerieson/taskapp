/*
 * Chart colors, read from the active daisyUI theme's CSS variables so charts follow
 * light and dark mode. Recharts draws SVG attributes, which cannot use var(), so the
 * values are resolved here and re-read whenever the theme changes.
 */
import { useTheme, type ThemeName } from './theme'

export interface ChartColors {
  /** The data series (one series per chart on the personal dashboard). */
  series: string
  /** Hover highlight behind a bar. */
  cursor: string
  /** Axis tick labels (drawn at reduced opacity, see `axisTick`). */
  axisText: string
  /** Grid lines and axis lines: recessive. */
  grid: string
  /** Chart surface, used for the gap ring around line markers. */
  surface: string
}

const cache = new Map<ThemeName, ChartColors>()

function cssVar(style: CSSStyleDeclaration, name: string, fallback: string): string {
  return style.getPropertyValue(name).trim() || fallback
}

function read(): ChartColors {
  const style = getComputedStyle(document.documentElement)
  const content = cssVar(style, '--color-base-content', 'currentColor')
  return {
    series: cssVar(style, '--color-primary', content),
    cursor: cssVar(style, '--color-base-200', 'transparent'),
    axisText: content,
    grid: cssVar(style, '--color-base-300', content),
    surface: cssVar(style, '--color-base-100', 'transparent'),
  }
}

/** The current theme's chart colors; re-renders the caller when the theme changes. */
export function useChartColors(): ChartColors {
  const { theme } = useTheme()
  let colors = cache.get(theme)
  if (!colors) {
    colors = read()
    cache.set(theme, colors)
  }
  return colors
}

/** Props for Recharts' `tick`: muted body text, small. */
export function axisTick(colors: ChartColors) {
  return { fill: colors.axisText, fillOpacity: 0.8, fontSize: 12 }
}

/** Recharts passes the hovered data row as `payload[0].payload`. */
export function hoveredRow<T>(props: {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: T }>
}): T | undefined {
  return props.active ? props.payload?.[0]?.payload : undefined
}
