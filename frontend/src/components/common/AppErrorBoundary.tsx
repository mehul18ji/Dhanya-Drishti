import { Component, type ErrorInfo, type ReactNode } from 'react'

import { BrandMark } from '../layout/Brand'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Last line of defence against a blank white screen. Render errors are rare, but
 * a deployed dashboard should still explain what happened and offer a safe way
 * back instead of crashing.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the details in the console for debugging; never render a stack trace.
    console.error('Unhandled dashboard error', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-50 px-4 py-16 dark:bg-ink-950">
        <main className="card w-full max-w-lg p-6 text-center sm:p-8" role="alert">
          <div className="flex justify-center">
            <BrandMark className="h-12 w-12" />
          </div>
          <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-700 dark:text-accent-300">
            DhanyaDrishti
          </p>
          <h1 className="mt-1 font-display text-2xl font-medium text-ink-900 dark:text-ink-50">
            Something went wrong
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
            The dashboard hit an unexpected display error. Your image was not uploaded from this
            screen, and the temporary history on the server is unaffected. Reload to continue.
          </p>
          <div className="mt-5 flex flex-col justify-center gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex w-full items-center justify-center rounded-lg bg-accent-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-700 sm:w-auto"
            >
              Reload dashboard
            </button>
            <a
              href="/"
              className="inline-flex w-full items-center justify-center rounded-lg border border-ink-300 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 sm:w-auto dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100"
            >
              Go to the analyzer
            </a>
          </div>
          <p className="mt-4 text-[11px] text-ink-500 dark:text-ink-400">
            If this repeats, check the browser console and the backend service log.
          </p>
        </main>
      </div>
    )
  }
}
