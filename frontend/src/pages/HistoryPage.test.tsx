import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '../services/api'
import {
  errorEnvelope,
  jsonResponse,
  makeHistoryItem,
} from '../test/fixtures'
import { SEVERITY_DISCLAIMER } from '../utils/disclaimers'
import { HistoryPage } from './HistoryPage'

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HistoryPage />
    </MemoryRouter>,
  )
}

describe('HistoryPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders labelled records, filters rejected rows and shows margins honestly', async () => {
    const predicted = makeHistoryItem()
    const uncertain = makeHistoryItem({
      prediction_id: 'uncertain-id',
      status: 'uncertain',
      disease: 'leaf_smut',
      severity: null,
      severity_reason_code: 'LESION_ESTIMATE_UNRELIABLE',
      lesion_area_percentage: null,
      lesion_reliable: false,
      margin: 0.31,
      warnings: ['BLURRY_IMAGE'],
      missing_features: ['lesion_area_ratio'],
    })
    const rejected = makeHistoryItem({
      prediction_id: 'rejected-id',
      status: 'rejected',
      disease: null,
      severity: null,
      lesion_area_percentage: null,
      lesion_reliable: false,
    })
    fetchMock.mockResolvedValue(
      jsonResponse({
        count: 3,
        items: [predicted, uncertain, rejected],
        runtime_storage: 'temporary',
      }),
    )

    renderPage()

    const rows = await screen.findAllByTestId('history-row')
    expect(rows).toHaveLength(2)
    expect(screen.queryByText('Rejected upload')).not.toBeInTheDocument()
    expect(screen.getByTestId('history-count')).toHaveTextContent('2 records')

    expect(screen.getAllByText('Brown Spot').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Leaf Smut').length).toBeGreaterThan(0)
    expect(screen.getByText('Predicted')).toBeInTheDocument()
    expect(screen.getByText('Uncertain')).toBeInTheDocument()
    expect(screen.getByText('12.4%')).toBeInTheDocument()
    expect(screen.getByText('Not available')).toBeInTheDocument()
    expect(screen.getByText('+1.13')).toBeInTheDocument()
    expect(screen.getAllByText('not a probability').length).toBe(2)
    expect(screen.getByText(/appears blurry/i)).toBeInTheDocument()
    expect(screen.getByText('lesion_area_ratio')).toBeInTheDocument()
    expect(screen.getByText(SEVERITY_DISCLAIMER)).toBeInTheDocument()
    expect(screen.queryByText(/\d+% confidence/i)).not.toBeInTheDocument()

    const artifact = within(rows[0]).getByRole('link', {
      name: /open temporary image artifact/i,
    })
    expect(artifact).toHaveAttribute(
      'href',
      `${API_BASE_URL}/api/v1/history/${predicted.prediction_id}/original`,
    )
    expect(artifact).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows an empty state when no labels have been stored', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ count: 0, items: [], runtime_storage: 'temporary' }),
    )

    renderPage()

    expect(await screen.findByTestId('history-empty')).toBeInTheDocument()
    expect(screen.getByText(/no predictions yet/i)).toBeInTheDocument()
    expect(screen.queryByTestId('history-row')).not.toBeInTheDocument()
  })

  it('shows a backend-waking error and can retry', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(
        jsonResponse({ count: 0, items: [], runtime_storage: 'temporary' }),
      )

    renderPage()

    expect(await screen.findByTestId('history-error')).toHaveTextContent(
      /starting analysis service/i,
    )
    await userEvent.setup().click(screen.getByRole('button', { name: /^retry$/i }))

    expect(await screen.findByTestId('history-empty')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('clears history after an explicit confirmation', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return Promise.resolve(
          jsonResponse({ deleted: 2, runtime_storage: 'temporary' }),
        )
      }
      return Promise.resolve(
        jsonResponse({
          count: 2,
          items: [makeHistoryItem(), makeHistoryItem({ prediction_id: 'second-id' })],
          runtime_storage: 'temporary',
        }),
      )
    })

    renderPage()
    await screen.findAllByTestId('history-row')

    await userEvent.setup().click(screen.getByRole('button', { name: /clear history/i }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(/cannot be undone/i)
    await userEvent.setup().click(
      within(dialog).getByRole('button', { name: /clear history/i }),
    )

    await waitFor(() => expect(screen.getByTestId('history-empty')).toBeInTheDocument())
    expect(screen.getByText(/removed 2 temporary records/i)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/history'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('keeps the records when clearing fails', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      return Promise.resolve(
        jsonResponse({
          count: 1,
          items: [makeHistoryItem()],
          runtime_storage: 'temporary',
        }),
      )
    })

    renderPage()
    await screen.findByTestId('history-row')

    await userEvent.setup().click(screen.getByRole('button', { name: /clear history/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.setup().click(
      within(dialog).getByRole('button', { name: /clear history/i }),
    )

    expect(await screen.findByTestId('clear-history-error')).toHaveTextContent(
      /starting analysis service/i,
    )
    expect(screen.getByTestId('history-row')).toBeInTheDocument()
  })

  it('shows a loading state while the request is pending', async () => {
    let resolve!: (response: Response) => void
    fetchMock.mockReturnValue(new Promise<Response>((done) => (resolve = done)))

    renderPage()
    expect(screen.getByTestId('history-loading')).toBeInTheDocument()

    resolve(jsonResponse({ count: 0, items: [], runtime_storage: 'temporary' }))
    expect(await screen.findByTestId('history-empty')).toBeInTheDocument()
  })

  it('maps a 404 clear failure to a readable error', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return Promise.resolve(
          errorEnvelope(404, 'PREDICTION_NOT_FOUND', 'No record.'),
        )
      }
      return Promise.resolve(
        jsonResponse({
          count: 1,
          items: [makeHistoryItem()],
          runtime_storage: 'temporary',
        }),
      )
    })

    renderPage()
    await screen.findByTestId('history-row')
    await userEvent.setup().click(screen.getByRole('button', { name: /clear history/i }))
    await userEvent.setup().click(
      within(screen.getByRole('dialog')).getByRole('button', { name: /clear history/i }),
    )

    expect(await screen.findByTestId('clear-history-error')).toHaveTextContent(
      /prediction not found/i,
    )
  })
})
