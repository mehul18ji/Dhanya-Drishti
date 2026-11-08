import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, makeHealth } from '../../test/fixtures'
import { Header } from './Header'

describe('Header health handling', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('reports a loaded model and allows a status refresh', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeHealth()))
    const user = userEvent.setup()

    render(<Header />)

    const badge = await screen.findByRole('button', {
      name: /refresh backend and model status/i,
    })
    expect(badge).toHaveTextContent(/backend online/i)
    expect(badge).toHaveTextContent(/svm-v1.0.0/)

    await user.click(badge)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('distinguishes backend-online from model-ready', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(makeHealth({ model_loaded: false, model_version: null })),
    )

    render(<Header />)

    expect(
      await screen.findByRole('button', { name: /refresh backend and model status/i }),
    ).toHaveTextContent(/backend online · model starting/i)
  })

  it('reports an unreachable backend', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<Header />)

    expect(
      await screen.findByRole('button', { name: /refresh backend and model status/i }),
    ).toHaveTextContent(/backend offline/i)
  })
})
