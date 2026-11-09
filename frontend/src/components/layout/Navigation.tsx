import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Analyze Leaf', end: true },
  { to: '/history', label: 'Prediction History', end: false },
  { to: '/about', label: 'About Model', end: false },
]

export function Navigation() {
  return (
    <nav aria-label="Primary" className="border-b border-ink-200/70 bg-white/60 backdrop-blur">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <ul className="no-scrollbar flex gap-1 overflow-x-auto py-2">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  [
                    'inline-flex min-h-[40px] items-center whitespace-nowrap rounded-full px-3.5 text-[13px] font-semibold transition-colors sm:px-4 sm:text-sm',
                    isActive
                      ? 'bg-ink-900 text-white shadow-sm dark:bg-accent-400 dark:text-ink-950'
                      : 'text-ink-600 hover:bg-ink-100/80 hover:text-ink-900 dark:text-ink-300 dark:hover:bg-white/10 dark:hover:text-white',
                  ].join(' ')
                }
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}
