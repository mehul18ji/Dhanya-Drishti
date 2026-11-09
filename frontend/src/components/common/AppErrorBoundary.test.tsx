import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppErrorBoundary } from './AppErrorBoundary'

function BrokenScreen(): never {
  throw new Error('render exploded with a secret stack')
}

describe('AppErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows a recovery screen instead of a blank page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <AppErrorBoundary>
        <BrokenScreen />
      </AppErrorBoundary>,
    )

    expect(
      screen.getByRole('heading', { name: /something went wrong/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /go to the analyzer/i })).toHaveAttribute(
      'href',
      '/',
    )
    expect(screen.queryByText(/secret stack/i)).not.toBeInTheDocument()
  })
})
