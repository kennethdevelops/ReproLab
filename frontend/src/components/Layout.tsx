import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Projects', end: true },
  { to: '/investigate', label: 'New investigation', end: false },
  { to: '/explore', label: 'RAG Explorer', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <span className="font-mono text-sm font-semibold tracking-tight">ReproLab</span>
          <nav aria-label="Main" className="flex gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm ${
                    isActive
                      ? 'bg-slate-100 font-medium dark:bg-slate-800'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  )
}
