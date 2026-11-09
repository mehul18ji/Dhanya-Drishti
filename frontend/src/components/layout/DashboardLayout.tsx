import { Outlet } from 'react-router-dom'

import { BackendHealthProvider } from '../../hooks/useBackendHealth'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { Footer } from './Footer'
import { Header } from './Header'
import { Navigation } from './Navigation'

export function DashboardLayout() {
  const online = useOnlineStatus()

  return (
    <BackendHealthProvider>
      <div className="relative flex min-h-screen flex-col overflow-x-clip">
        <div
          aria-hidden="true"
          className="paper-grain pointer-events-none fixed inset-0 -z-10 opacity-[0.035] dark:opacity-[0.05]"
        />
        <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-32 top-24 h-64 w-64 rounded-full bg-accent-400/15 blur-3xl sm:h-80 sm:w-80" />
          <div className="absolute -right-24 top-1/3 h-72 w-72 rounded-full bg-warn-300/10 blur-3xl sm:h-96 sm:w-96" />
          <svg
            viewBox="0 0 24 24"
            className="absolute right-8 top-40 hidden h-24 w-24 rotate-12 text-accent-700/10 dark:text-accent-300/10 lg:block"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 21c0-6 3.5-10.5 8-12-1 6-4 9.5-8 12Z" />
            <path d="M12 21C12 15 8.5 10.5 4 9c1 6 4 9.5 8 12Z" />
            <path d="M12 21v-7" />
          </svg>
        </div>

        <Header />
        <Navigation />
        {!online ? (
          <div
            role="status"
            data-testid="offline-banner"
            className="border-b border-warn-300 bg-warn-50 px-4 py-2 text-center text-xs font-medium text-warn-900 dark:border-warn-700 dark:bg-warn-900/25 dark:text-warn-100"
          >
            You are offline. Reconnect to continue — the dashboard recovers automatically when the
            connection returns.
          </div>
        ) : null}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-10 pt-5 sm:px-6 sm:pt-6 lg:px-8 lg:pb-14 lg:pt-8">
          <Outlet />
        </main>
        <Footer />
      </div>
    </BackendHealthProvider>
  )
}
