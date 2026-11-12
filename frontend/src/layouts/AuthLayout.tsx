import type { ReactNode } from 'react'

import Brand from '../components/Brand'
import ThemeToggle from '../components/ThemeToggle'

interface AuthLayoutProps {
  title: string
  subtitle?: ReactNode
  children: ReactNode
}

/** Centered card for the public pages (login, invite, password reset). */
export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-base-200 text-base-content">
      <header className="flex items-center justify-between p-4">
        <Brand />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-10 sm:items-center">
        <div className="card w-full max-w-sm border border-base-300 bg-base-100 shadow-sm">
          <div className="card-body gap-4 p-5 sm:p-8">
            <div>
              <h1 className="text-2xl font-bold">{title}</h1>
              {subtitle && <div className="mt-1 text-sm text-base-content/80">{subtitle}</div>}
            </div>
            {children}
          </div>
        </div>
      </main>
    </div>
  )
}
