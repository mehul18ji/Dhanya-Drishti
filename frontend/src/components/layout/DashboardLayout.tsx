import { Outlet } from 'react-router-dom'

import { Footer } from './Footer'
import { Header } from './Header'
import { Navigation } from './Navigation'

export function DashboardLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-ink-50">
      <Header />
      <Navigation />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
