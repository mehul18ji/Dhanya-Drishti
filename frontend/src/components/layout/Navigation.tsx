import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Analyze Leaf', end: true },
  { to: '/history', label: 'Prediction History', end: false },
  { to: '/about', label: 'About Model', end: false },
]

export function Navigation() {
  return (
    <nav aria-label="Primary" className="border-b border-ink-200 bg-white">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <ul className="flex gap-1 overflow-x-auto">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  [
                    'inline-block whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium transition-colors',
                    isActive
                      ? 'border-accent-500 text-ink-900'
                      : 'border-transparent text-ink-500 hover:border-ink-300 hover:text-ink-800',
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
