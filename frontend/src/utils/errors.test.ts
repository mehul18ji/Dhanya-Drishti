import { describe, expect, it } from 'vitest'

import { ApiError } from '../services/api'
import { describeApiError } from './errors'

describe('friendly error mapping', () => {
  it('keeps 413, 415, 422 and 503 distinct', () => {
    const fileTooLarge = describeApiError(
      new ApiError('too big', { kind: 'http', status: 413, reasonCode: 'FILE_TOO_LARGE' }),
    )
    expect(fileTooLarge.title).toBe('File too large')
    expect(fileTooLarge.retryable).toBe(false)

    const unsupported = describeApiError(
      new ApiError('bad type', {
        kind: 'http',
        status: 415,
        reasonCode: 'UNSUPPORTED_FILE_TYPE',
      }),
    )
    expect(unsupported.title).toBe('Unsupported file type')

    const tooSmall = describeApiError(
      new ApiError('too small', {
        kind: 'http',
        status: 422,
        reasonCode: 'IMAGE_TOO_SMALL',
      }),
    )
    expect(tooSmall.title).toBe('Image too small')

    const corrupt = describeApiError(
      new ApiError('corrupt', { kind: 'http', status: 422, reasonCode: 'INVALID_UPLOAD' }),
    )
    expect(corrupt.title).toBe('Image could not be read')

    const starting = describeApiError(
      new ApiError('not loaded', {
        kind: 'http',
        status: 503,
        reasonCode: 'MODEL_NOT_LOADED',
      }),
    )
    expect(starting.title).toMatch(/starting/i)
    expect(starting.tone).toBe('warning')
    expect(starting.retryable).toBe(true)
  })

  it('explains cold-start and network failures as retryable', () => {
    const network = describeApiError(new ApiError('no route', { kind: 'network' }))
    expect(network.title).toBe('Starting analysis service…')
    expect(network.retryable).toBe(true)

    const timeout = describeApiError(new ApiError('slow', { kind: 'timeout' }))
    expect(timeout.title).toMatch(/slow to respond/i)
  })

  it('maps history 404 separately from a prediction failure', () => {
    const notFound = describeApiError(
      new ApiError('gone', {
        kind: 'http',
        status: 404,
        reasonCode: 'PREDICTION_NOT_FOUND',
      }),
      'history',
    )
    expect(notFound.title).toBe('Prediction not found')
    expect(notFound.retryable).toBe(false)
  })

  it('handles unknown failures without exposing internals', () => {
    const unknown = describeApiError(new Error('secret stack trace'))
    expect(unknown.title).toBe('Unexpected error')
    expect(unknown.message).not.toContain('secret stack trace')
  })

  it('explains a missing deployment configuration without offering a useless retry', () => {
    const config = describeApiError(
      new ApiError('Set VITE_API_BASE_URL and redeploy.', { kind: 'config' }),
    )

    expect(config.title).toMatch(/not configured/i)
    expect(config.retryable).toBe(false)
    expect(config.message).toMatch(/VITE_API_BASE_URL/)
  })

  it('treats gateway 502/503/504 as a waking free-tier backend', () => {
    for (const status of [502, 503, 504]) {
      const waking = describeApiError(new ApiError('gateway', { kind: 'http', status }))
      expect(waking.title).toMatch(/waking up/i)
      expect(waking.tone).toBe('warning')
      expect(waking.retryable).toBe(true)
    }
  })
})
