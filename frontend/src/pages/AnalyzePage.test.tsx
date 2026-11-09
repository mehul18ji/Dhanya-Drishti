import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  errorEnvelope,
  jsonResponse,
  makeFile,
  makeHealth,
  makePrediction,
  makeRejected,
} from '../test/fixtures'
import { BackendHealthProvider } from '../hooks/useBackendHealth'
import { UNCERTAIN_NOTICE } from '../utils/disclaimers'
import { AnalyzePage } from './AnalyzePage'

function renderPage() {
  return render(
    <BackendHealthProvider>
      <AnalyzePage />
    </BackendHealthProvider>,
  )
}

function selectFile() {
  const input = document.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('file input not found')
  fireEvent.change(input, {
    target: { files: [makeFile({ name: 'leaf.jpg' })] },
  })
}

describe('AnalyzePage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('runs upload → preview → analysed prediction', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      if (url.endsWith('/api/v1/predict')) {
        return Promise.resolve(jsonResponse(makePrediction()))
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`))
    })
    const user = userEvent.setup()

    renderPage()
    expect(await screen.findByTestId('model-ready')).toBeInTheDocument()

    selectFile()
    expect(screen.getByTestId('image-preview')).toBeInTheDocument()
    const analyze = screen.getByRole('button', { name: /analyze leaf/i })
    expect(analyze).toBeEnabled()

    await user.click(analyze)

    expect(await screen.findByTestId('prediction-result')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Brown Spot' })).toBeInTheDocument()
    expect(screen.getByText('Predicted')).toBeInTheDocument()
    expect(screen.queryByTestId('analysis-progress')).not.toBeInTheDocument()

    const predictCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith('/api/v1/predict'),
    )
    expect(predictCall).toBeDefined()
    expect((predictCall?.[1] as RequestInit).body).toBeInstanceOf(FormData)
    expect(screen.queryByText(/confidence\s*[:=]\s*\d/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\d+% confidence/i)).not.toBeInTheDocument()
  })

  it('shows a staged loading indicator while the backend is working', async () => {
    let resolvePredict!: (response: Response) => void
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      if (url.endsWith('/api/v1/predict')) {
        return new Promise<Response>((done) => (resolvePredict = done))
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`))
    })
    const user = userEvent.setup()

    renderPage()
    await screen.findByTestId('model-ready')
    selectFile()
    await user.click(screen.getByRole('button', { name: /analyze leaf/i }))

    expect(screen.getByTestId('analysis-progress')).toBeInTheDocument()
    expect(screen.getByText(/stage labels are approximate/i)).toBeInTheDocument()

    await act(async () => {
      resolvePredict(jsonResponse(makePrediction()))
    })

    expect(await screen.findByTestId('prediction-result')).toBeInTheDocument()
  })

  it('presents an uncertain prediction with the required safeguard text', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      return Promise.resolve(jsonResponse(makePrediction({ status: 'uncertain' })))
    })
    const user = userEvent.setup()

    renderPage()
    await screen.findByTestId('model-ready')
    selectFile()
    await user.click(screen.getByRole('button', { name: /analyze leaf/i }))

    expect(await screen.findByTestId('prediction-result')).toHaveAttribute(
      'data-status',
      'uncertain',
    )
    expect(screen.getByText(UNCERTAIN_NOTICE)).toBeInTheDocument()
  })

  it('presents a 200 rejection as a rejected upload, not a disease result', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      return Promise.resolve(jsonResponse(makeRejected()))
    })
    const user = userEvent.setup()

    renderPage()
    await screen.findByTestId('model-ready')
    selectFile()
    await user.click(screen.getByRole('button', { name: /analyze leaf/i }))

    expect(await screen.findByTestId('rejected-result')).toBeInTheDocument()
    expect(screen.queryByTestId('prediction-result')).not.toBeInTheDocument()
    expect(screen.queryByTestId('severity-badge')).not.toBeInTheDocument()
    expect(screen.getByText(/not added to temporary prediction history/i)).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.every(([url]) => !String(url).includes('/history')),
    ).toBe(true)
  })

  it('keeps upload-level 413 errors distinct from a rejection', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      return Promise.resolve(
        errorEnvelope(413, 'FILE_TOO_LARGE', 'Upload exceeds the 10 MB limit.'),
      )
    })
    const user = userEvent.setup()

    renderPage()
    await screen.findByTestId('model-ready')
    selectFile()
    await user.click(screen.getByRole('button', { name: /analyze leaf/i }))

    const error = await screen.findByTestId('analysis-error')
    expect(error).toHaveTextContent(/file too large/i)
    expect(error).toHaveTextContent(/upload-level failures/i)
    expect(screen.queryByTestId('rejected-result')).not.toBeInTheDocument()
    expect(screen.queryByTestId('prediction-result')).not.toBeInTheDocument()
  })

  it('shows a model-unavailable 503 as a retryable service error', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      return Promise.resolve(
        errorEnvelope(503, 'MODEL_NOT_LOADED', 'Production model not loaded.'),
      )
    })
    const user = userEvent.setup()

    renderPage()
    await screen.findByTestId('model-ready')
    selectFile()
    await user.click(screen.getByRole('button', { name: /analyze leaf/i }))

    const error = await screen.findByTestId('analysis-error')
    expect(error).toHaveTextContent(/analysis service is starting/i)
    expect(screen.getByRole('button', { name: /^retry$/i })).toBeInTheDocument()
  })

  it('disables analysis while the backend is unavailable and recovers on retry', async () => {
    let healthCalls = 0
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        healthCalls += 1
        if (healthCalls === 1) return Promise.reject(new TypeError('Failed to fetch'))
        return Promise.resolve(jsonResponse(makeHealth()))
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`))
    })
    const user = userEvent.setup()

    renderPage()
    expect(await screen.findByTestId('backend-unavailable')).toHaveTextContent(
      /starting analysis service/i,
    )

    expect(screen.getByTestId('upload-dropzone')).toHaveAttribute('aria-disabled', 'true')
    const analyze = screen.getByRole('button', { name: /analyze leaf/i })
    expect(analyze).toBeDisabled()
    expect(screen.queryByTestId('model-ready')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry connection/i }))

    expect(await screen.findByTestId('model-ready')).toBeInTheDocument()
    selectFile()
    expect(screen.getByRole('button', { name: /analyze leaf/i })).toBeEnabled()
  })

  it('disables analysis when the backend is online but the model is still loading', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/api/v1/health')) {
        return Promise.resolve(
          jsonResponse(makeHealth({ model_loaded: false, model_version: null })),
        )
      }
      return Promise.reject(new Error('predict should not be called'))
    })

    renderPage()
    expect(await screen.findByTestId('model-unavailable')).toBeInTheDocument()
    expect(screen.getByTestId('upload-dropzone')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: /analyze leaf/i })).toBeDisabled()
  })
})
