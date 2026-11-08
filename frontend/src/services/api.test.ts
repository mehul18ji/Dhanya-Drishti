import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  ApiError,
  artifactUrl,
  deleteHistory,
  getHealth,
  getHistory,
  predict,
} from '../services/api'
import {
  errorEnvelope,
  jsonResponse,
  makeFile,
  makeHealth,
  makeRejected,
} from '../test/fixtures'

describe('typed API client', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads /health from the configured base URL', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeHealth()))

    await expect(getHealth()).resolves.toMatchObject({
      status: 'ok',
      model_loaded: true,
      model_version: 'svm-v1.0.0',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/api/v1/health`,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Accept: 'application/json' }),
      }),
    )
  })

  it('uploads multipart form data with the documented file field', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRejected()))
    const file = makeFile({ name: 'leaf.jpg' })

    await predict(file)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE_URL}/api/v1/predict`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    const sent = (init.body as FormData).get('file')
    expect(sent).toBeInstanceOf(File)
    expect((sent as File).name).toBe('leaf.jpg')
  })

  it('maps 413 to a typed file-too-large error', async () => {
    fetchMock.mockResolvedValue(
      errorEnvelope(413, 'FILE_TOO_LARGE', 'Upload exceeds the 10 MB limit.'),
    )

    await expect(predict(makeFile())).rejects.toMatchObject({
      kind: 'http',
      status: 413,
      reasonCode: 'FILE_TOO_LARGE',
    })
  })

  it('maps 415 and 422 and 503 to typed errors', async () => {
    const cases = [
      [415, 'UNSUPPORTED_FILE_TYPE'],
      [422, 'INVALID_UPLOAD'],
      [503, 'MODEL_NOT_LOADED'],
    ] as const

    for (const [status, reason] of cases) {
      fetchMock.mockResolvedValueOnce(errorEnvelope(status, reason, 'Backend says no.'))
      await expect(predict(makeFile())).rejects.toMatchObject({
        kind: 'http',
        status,
        reasonCode: reason,
      })
    }
  })

  it('reports a network failure without leaking an exception type', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(getHealth()).rejects.toMatchObject({
      kind: 'network',
      status: null,
      reasonCode: null,
    })
  })

  it('reports a timeout when the request exceeds its budget', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )

    const request = getHealth()
    const assertion = expect(request).rejects.toMatchObject({ kind: 'timeout' })
    await vi.advanceTimersByTimeAsync(6_000)
    await assertion
  })

  it('rejects an unreadable success body', async () => {
    fetchMock.mockResolvedValue(new Response('this is not json', { status: 200 }))

    await expect(getHealth()).rejects.toMatchObject({ kind: 'invalid-response' })
  })

  it('builds safe artifact URLs and leaves absolute URLs alone', () => {
    expect(artifactUrl('/api/v1/history/id/original')).toBe(
      `${API_BASE_URL}/api/v1/history/id/original`,
    )
    expect(artifactUrl('https://example.org/mask.png')).toBe('https://example.org/mask.png')
    expect(artifactUrl(null)).toBeNull()
  })

  it('clamps the history limit and uses DELETE for clearing', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ count: 0, items: [], runtime_storage: 'temporary' }))
    await getHistory(500)
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/api/v1/history?limit=200`)

    fetchMock.mockResolvedValue(jsonResponse({ deleted: 2, runtime_storage: 'temporary' }))
    await expect(deleteHistory()).resolves.toMatchObject({ deleted: 2 })
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' })
  })

  it('exposes ApiError as the only client error type', async () => {
    fetchMock.mockResolvedValue(errorEnvelope(500, 'INTERNAL_ERROR', 'boom'))
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError)
  })
})
