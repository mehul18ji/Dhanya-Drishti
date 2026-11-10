import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  errorEnvelope,
  jsonResponse,
  makeModelInfo,
} from '../test/fixtures'
import { SEVERITY_DISCLAIMER } from '../utils/disclaimers'
import { AboutModelPage } from './AboutModelPage'

describe('AboutModelPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders the loaded bundle, metrics, classes and disclaimers', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeModelInfo()))

    render(<AboutModelPage />)

    expect(await screen.findByTestId('model-info')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /support vector machine/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('0.841 ± 0.060')).toBeInTheDocument()
    expect(screen.getByText('0.785')).toBeInTheDocument()
    expect(screen.getByText('50 features')).toBeInTheDocument()
    expect(screen.getByText('96')).toBeInTheDocument()

    expect(
      screen.getByRole('heading', { name: /candidates compared during development/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('0.7935 ± 0.0387')).toBeInTheDocument()
    expect(screen.getByText('0.7507 ± 0.0853')).toBeInTheDocument()
    expect(screen.getByText('0.8440')).toBeInTheDocument()
    expect(screen.getByText('0.8006')).toBeInTheDocument()
    expect(screen.getByText('0.7602')).toBeInTheDocument()
    expect(screen.getAllByText('Not evaluated')).toHaveLength(2)

    expect(screen.getByText('Decision margins, not probabilities')).toBeInTheDocument()
    expect(screen.getByText(/calibrated probabilities: no/i)).toBeInTheDocument()
    expect(screen.getByText(/there is no healthy class/i)).toBeInTheDocument()
    expect(screen.getByText('Bacterial Leaf Blight')).toBeInTheDocument()
    expect(screen.getByText('Brown Spot')).toBeInTheDocument()
    expect(screen.getByText('Leaf Smut')).toBeInTheDocument()
    expect(screen.getByText(SEVERITY_DISCLAIMER)).toBeInTheDocument()
    expect(screen.getByText(/white-paper studio photographs/i)).toBeInTheDocument()
    expect(screen.getByText(/120 rice-leaf images/i)).toBeInTheDocument()
    expect(screen.getByText(/no confidence percentage/i)).toBeInTheDocument()

    expect(screen.queryByText(/confidence\s*[:=]\s*\d/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^healthy$/i)).not.toBeInTheDocument()
  })

  it('shows a loading state before model info arrives', () => {
    let resolve!: (response: Response) => void
    fetchMock.mockReturnValue(new Promise<Response>((done) => (resolve = done)))

    render(<AboutModelPage />)
    expect(screen.getByTestId('model-info-loading')).toBeInTheDocument()

    resolve(jsonResponse(makeModelInfo()))
    // The component updates after the promise resolves; the next test's cleanup
    // handles unmounting. Assert success asynchronously.
    return screen.findByTestId('model-info')
  })

  it('maps a 503 to the cold-start message and offers a retry', async () => {
    fetchMock.mockResolvedValue(
      errorEnvelope(503, 'MODEL_NOT_LOADED', 'Production model not loaded.'),
    )

    render(<AboutModelPage />)

    const error = await screen.findByTestId('model-info-error')
    expect(error).toHaveTextContent(/analysis service is starting/i)
    expect(screen.getByRole('button', { name: /^retry$/i })).toBeInTheDocument()
  })
})
