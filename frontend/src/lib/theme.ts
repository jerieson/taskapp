/*
 * Theme store. The choice ("light", "dark" or "system") is kept in localStorage and
 * the resolved daisyUI theme is written to <html data-theme>.
 *
 * index.html runs an inline copy of the resolve step before first paint, so keep
 * THEME_STORAGE_KEY and the theme names in sync with it.
 */
import { useSyncExternalStore } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'
export type ThemeName = 'brand-light' | 'brand-dark'

export const THEME_STORAGE_KEY = 'taskapp-theme'

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
const listeners = new Set<() => void>()

function readMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

let mode: ThemeMode = readMode()

function resolveTheme(): ThemeName {
  if (mode === 'system') return darkQuery.matches ? 'brand-dark' : 'brand-light'
  return mode === 'dark' ? 'brand-dark' : 'brand-light'
}

function apply() {
  document.documentElement.setAttribute('data-theme', resolveTheme())
  listeners.forEach((listener) => listener())
}

darkQuery.addEventListener('change', () => {
  if (mode === 'system') apply()
})

// Keep other open tabs in step with a change made here.
window.addEventListener('storage', (event) => {
  if (event.key === THEME_STORAGE_KEY) {
    mode = readMode()
    apply()
  }
})

export function setThemeMode(next: ThemeMode) {
  mode = next
  try {
    if (next === 'system') localStorage.removeItem(THEME_STORAGE_KEY)
    else localStorage.setItem(THEME_STORAGE_KEY, next)
  } catch {
    // Storage blocked (private mode etc.): the choice lasts for this page only.
  }
  apply()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Current theme choice and resolved theme; re-renders when either changes. */
export function useTheme() {
  const currentMode = useSyncExternalStore(subscribe, () => mode)
  const theme = useSyncExternalStore(subscribe, resolveTheme)
  return {
    mode: currentMode,
    theme,
    setMode: setThemeMode,
    toggle: () => setThemeMode(theme === 'brand-dark' ? 'light' : 'dark'),
  }
}
