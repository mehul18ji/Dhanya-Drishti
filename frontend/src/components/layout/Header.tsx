import { Link } from 'react-router-dom'

import { useBackendHealth } from '../../hooks/useBackendHealth'
import { BackendStatus } from './BackendStatus'
import { BrandMark } from './Brand'
import { ThemeToggle } from './ThemeToggle'

export function Header() {
  const health = useBackendHealth()

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-ink-950/95 text-white backdrop-blur supports-[backdrop-filter]:bg-ink-950/85">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-3.5 lg:px-8">
        <Link
          to="/"
          aria-label="DhanyaDrishti home"
          className="group flex min-w-0 items-center gap-3 rounded-xl focus-visible:ring-offset-ink-950"
        >
          <BrandMark className="h-10 w-10 shrink-0 drop-shadow-sm transition-transform duration-300 group-hover:-rotate-3 sm:h-11 sm:w-11" />
          <span className="min-w-0">
            <span className="block truncate text-[17px] font-bold leading-tight tracking-tight sm:text-lg">
              DhanyaDrishti
            </span>
            <span className="mt-0.5 hidden text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-300/80 sm:block">
              Rice-leaf diagnostics
            </span>
          </span>
        </Link>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <BackendStatus health={health} />
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
