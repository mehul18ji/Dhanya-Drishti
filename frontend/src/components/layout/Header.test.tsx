import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BackendHealthContext } from '../../hooks/useBackendHealth'
import type { HealthState } from '../../hooks/useHealth'
import { Header } from './Header'

const connectedHealth: HealthState = {
  state: 'online',
  modelLoaded: true,
  modelVersion: 'svm-v1.0.0',
  lastChecked: new Date(),
  error: null,
  refresh: vi.fn(),
}

function renderHeader(health: HealthState = connectedHealth) {
  return render(
    <BackendHealthContext.Provider value={health}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Header />
      </MemoryRouter>
    </BackendHealthContext.Provider>,
  )
}

describe('Header', () => {
  beforeEach(() => {
    if (typeof window.localStorage?.clear === 'function') window.localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('shows the brand and a live backend connection badge', () => {
    renderHeader()

    expect(screen.getByText('DhanyaDrishti')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dhanyadrishti home/i })).toHaveAttribute('href', '/')
    const status = screen.getByTestId('backend-status')
    expect(status).toHaveTextContent('Connected')
    expect(status).toHaveTextContent('Local')
    expect(status).toHaveAttribute('data-state', 'online')
    expect(status).toHaveAttribute('data-target', 'local')
  })

  it('shows an offline backend without breaking the header actions', () => {
    renderHeader({
      ...connectedHealth,
      state: 'offline',
      modelLoaded: false,
      modelVersion: null,
    })

    const status = screen.getByTestId('backend-status')
    expect(status).toHaveTextContent(/backend offline/i)
    expect(status).toHaveAttribute('data-state', 'offline')
    expect(screen.getByRole('button', { name: /switch to dark mode/i })).toBeInTheDocument()
  })

  it('keeps the theme toggle as the only header button', () => {
    renderHeader()

    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(screen.getByRole('button', { name: /switch to dark mode/i })).toBeInTheDocument()
  })

  it('toggles between dark and light mode', async () => {
    const user = userEvent.setup()
    renderHeader()

    await user.click(screen.getByRole('button', { name: /switch to dark mode/i }))

    expect(screen.getByRole('button', { name: /switch to light mode/i })).toBeInTheDocument()
    expect(document.documentElement).toHaveClass('dark')

    await user.click(screen.getByRole('button', { name: /switch to light mode/i }))

    expect(document.documentElement).not.toHaveClass('dark')
  })
})
