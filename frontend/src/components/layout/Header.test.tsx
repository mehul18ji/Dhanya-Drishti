import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { Header } from './Header'

function renderHeader() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Header />
    </MemoryRouter>,
  )
}

describe('Header', () => {
  beforeEach(() => {
    if (typeof window.localStorage?.clear === 'function') window.localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('shows the rebranded name and hides backend/model status text', () => {
    renderHeader()

    expect(screen.getByText('DhanyaDrishti')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dhanyadrishti home/i })).toHaveAttribute('href', '/')
    expect(screen.queryByText(/backend online/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/backend offline/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/model: classical ml/i)).not.toBeInTheDocument()
  })

  it('keeps the theme toggle as the only header action', () => {
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
