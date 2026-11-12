import { useTheme } from '../lib/theme'
import { MoonIcon, SunIcon } from './icons'

/** Navbar button that switches between the light and dark theme. */
export default function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'brand-dark'
  const label = isDark ? 'Switch to light theme' : 'Switch to dark theme'
  return (
    <button
      type="button"
      className="btn btn-ghost btn-circle"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}
