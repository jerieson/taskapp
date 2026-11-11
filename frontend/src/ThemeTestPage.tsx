// TEMPORARY (Phase 0): checks both daisyUI themes. Replaced by the app shell in Phase 3.
import { useState } from 'react'

type ThemeChoice = 'system' | 'brand-light' | 'brand-dark'

const BRAND_COLORS = [
  {
    name: 'primary',
    btn: 'btn-primary',
    badge: 'badge-primary',
    surface: 'bg-primary text-primary-content',
  },
  {
    name: 'secondary',
    btn: 'btn-secondary',
    badge: 'badge-secondary',
    surface: 'bg-secondary text-secondary-content',
  },
  {
    name: 'accent',
    btn: 'btn-accent',
    badge: 'badge-accent',
    surface: 'bg-accent text-accent-content',
  },
  {
    name: 'neutral',
    btn: 'btn-neutral',
    badge: 'badge-neutral',
    surface: 'bg-neutral text-neutral-content',
  },
] as const

const STATUS_ALERTS = [
  { name: 'info', className: 'alert-info', badge: 'badge-info' },
  { name: 'success', className: 'alert-success', badge: 'badge-success' },
  { name: 'warning', className: 'alert-warning', badge: 'badge-warning' },
  { name: 'error', className: 'alert-error', badge: 'badge-error' },
] as const

function applyTheme(choice: ThemeChoice) {
  // No data-theme = daisyUI follows the system (brand-dark has prefersdark).
  if (choice === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', choice)
}

export default function ThemeTestPage() {
  const [theme, setTheme] = useState<ThemeChoice>('system')

  function choose(choice: ThemeChoice) {
    setTheme(choice)
    applyTheme(choice)
  }

  return (
    <main className="min-h-screen bg-base-200 text-base-content">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 sm:p-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold">Theme test</h1>
            <p className="text-sm opacity-70">Temporary Phase 0 page</p>
          </div>
          <div role="radiogroup" aria-label="Theme" className="join">
            {(['system', 'brand-light', 'brand-dark'] as const).map((choice) => (
              <input
                key={choice}
                type="radio"
                name="theme"
                className="btn join-item min-h-11"
                aria-label={
                  choice === 'system' ? 'System' : choice === 'brand-light' ? 'Light' : 'Dark'
                }
                checked={theme === choice}
                onChange={() => choose(choice)}
              />
            ))}
          </div>
        </header>

        <section className="card bg-base-100 shadow-sm">
          <div className="card-body gap-4">
            <h2 className="card-title">Buttons</h2>
            <div className="flex flex-wrap gap-2">
              {BRAND_COLORS.map((c) => (
                <button key={c.name} type="button" className={`btn ${c.btn}`}>
                  {c.name}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {BRAND_COLORS.map((c) => (
                <button key={c.name} type="button" className={`btn btn-outline ${c.btn}`}>
                  {c.name} outline
                </button>
              ))}
            </div>

            <h2 className="card-title">Badges</h2>
            <div className="flex flex-wrap gap-2">
              {BRAND_COLORS.map((c) => (
                <span key={c.name} className={`badge ${c.badge}`}>
                  {c.name}
                </span>
              ))}
              {STATUS_ALERTS.map((s) => (
                <span key={s.name} className={`badge ${s.badge}`}>
                  {s.name}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold">Cards</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {BRAND_COLORS.map((c) => (
              <div key={c.name} className={`card ${c.surface} shadow-sm`}>
                <div className="card-body">
                  <h3 className="card-title capitalize">{c.name}</h3>
                  <p className="text-sm">Content color on a {c.name} surface.</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Alerts</h2>
          {BRAND_COLORS.map((c) => (
            <div key={c.name} role="alert" className={`alert ${c.surface}`}>
              <span>
                <strong className="capitalize">{c.name}</strong> alert
              </span>
            </div>
          ))}
          {STATUS_ALERTS.map((s) => (
            <div key={s.name} role="alert" className={`alert ${s.className}`}>
              <span>
                <strong className="capitalize">{s.name}</strong> alert
              </span>
            </div>
          ))}
        </section>

        <section className="card bg-base-100 shadow-sm">
          <div className="card-body">
            <h2 className="card-title">Base surfaces</h2>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="rounded-box border border-base-300 bg-base-100 p-4">base-100</div>
              <div className="rounded-box bg-base-200 p-4">base-200</div>
              <div className="rounded-box bg-base-300 p-4">base-300</div>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
