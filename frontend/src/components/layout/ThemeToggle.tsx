import { useEffect, useState } from 'react'
import type { MouseEvent } from 'react'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'dhanyadrishti-theme'

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => {
    ready: Promise<void>
    finished: Promise<void>
  }
}

function preferredTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // Storage can be unavailable in private/embedded contexts.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(preferredTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const toggle = (event: MouseEvent<HTMLButtonElement>) => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    const rect = event.currentTarget.getBoundingClientRect()
    const x = rect.left + rect.width / 2
    const y = rect.top + rect.height / 2

    const persist = () => {
      applyTheme(next)
      setTheme(next)
      try {
        window.localStorage.setItem(STORAGE_KEY, next)
      } catch {
        // The theme still applies for this session.
      }
    }

    const doc = document as ViewTransitionDocument
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reducedMotion || typeof doc.startViewTransition !== 'function') {
      persist()
      return
    }

    const transition = doc.startViewTransition(persist)
    transition.ready
      .then(() => {
        const radius = Math.hypot(
          Math.max(x, window.innerWidth - x),
          Math.max(y, window.innerHeight - y),
        )
        document.documentElement.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${radius}px at ${x}px ${y}px)`,
            ],
          },
          {
            duration: 700,
            easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
            pseudoElement: '::view-transition-new(root)',
          },
        )
      })
      .catch(() => {
        // A cancelled transition simply leaves the committed theme in place.
      })
  }

  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="group inline-flex h-11 w-16 shrink-0 items-center justify-center rounded-full border border-white/25 bg-white/10 shadow-sm backdrop-blur transition-colors hover:border-accent-300/70 hover:bg-white/20 focus-visible:ring-offset-ink-950 sm:h-9 sm:w-14"
    >
      <span
        aria-hidden="true"
        className={`relative flex h-6 w-11 items-center rounded-full border border-white/20 transition-colors ${
          isDark ? 'bg-accent-500' : 'bg-ink-600'
        }`}
      >
        <span
          className={`flex h-5 w-5 items-center justify-center rounded-full bg-white text-ink-800 shadow transition-transform duration-300 ${
            isDark ? 'translate-x-[22px]' : 'translate-x-0.5'
          }`}
        >
          <svg
            viewBox="0 0 24 24"
            className="h-3 w-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {isDark ? (
              <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" />
            ) : (
              <>
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
              </>
            )}
          </svg>
        </span>
      </span>
    </button>
  )
}
