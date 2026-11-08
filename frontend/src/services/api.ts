import type {
  ErrorEnvelope,
  HealthResponse,
  HistoryDeleteResponse,
  HistoryItem,
  HistoryListResponse,
  ModelInfoResponse,
  PredictResponse,
} from '../types/api'

/** Backend base URL comes from VITE_API_BASE_URL (PRD §21). */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')

export const DEFAULT_UPLOAD_LIMIT_MB = 10

const HEALTH_TIMEOUT_MS = 6_000
const DEFAULT_TIMEOUT_MS = 20_000
/** CPU inference can be slow on first use, so /predict gets a wider budget. */
const PREDICT_TIMEOUT_MS = 90_000

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'aborted' | 'invalid-response'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly reasonCode: string | null

  constructor(
    message: string,
    options: {
      kind: ApiErrorKind
      status?: number | null
      reasonCode?: string | null
    },
  ) {
    super(message)
    this.name = 'ApiError'
    this.kind = options.kind
    this.status = options.status ?? null
    this.reasonCode = options.reasonCode ?? null
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: BodyInit
  headers?: Record<string, string>
  signal?: AbortSignal
  timeoutMs?: number
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return (
    record.status === 'error' &&
    typeof record.reason_code === 'string' &&
    typeof record.message === 'string'
  )
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController()
  let timedOut = false

  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS)

  const forwardAbort = () => controller.abort()
  if (options.signal) {
    if (options.signal.aborted) controller.abort()
    else options.signal.addEventListener('abort', forwardAbort)
  }

  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method: options.method ?? 'GET',
        headers: { Accept: 'application/json', ...options.headers },
        body: options.body,
        signal: controller.signal,
      })
    } catch (error) {
      if (options.signal?.aborted) {
        throw new ApiError('The request was cancelled.', { kind: 'aborted' })
      }
      if (timedOut) {
        throw new ApiError(
          'The analysis service did not answer in time. It may still be starting up.',
          { kind: 'timeout' },
        )
      }
      throw new ApiError(
        'Could not reach the analysis service. Check that the backend is running.',
        { kind: 'network' },
      )
    }

    const text = await response.text()
    let payload: unknown = null
    if (text.length > 0) {
      try {
        payload = JSON.parse(text)
      } catch {
        payload = null
      }
    }

    if (!response.ok) {
      const envelope = isErrorEnvelope(payload) ? payload : null
      throw new ApiError(
        envelope?.message ?? `The analysis service returned HTTP ${response.status}.`,
        {
          kind: 'http',
          status: response.status,
          reasonCode: envelope?.reason_code ?? null,
        },
      )
    }

    if (payload === null) {
      throw new ApiError('The analysis service returned an unreadable response.', {
        kind: 'invalid-response',
        status: response.status,
      })
    }

    return payload as T
  } finally {
    window.clearTimeout(timer)
    options.signal?.removeEventListener('abort', forwardAbort)
  }
}

/** Turn a relative or absolute artifact URL into a safe absolute URL. */
export function artifactUrl(url: string | null | undefined): string | null {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  return `${API_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`
}

/** GET /api/v1/health */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/api/v1/health', {
    signal,
    timeoutMs: HEALTH_TIMEOUT_MS,
  })
}

/** GET /api/v1/model-info */
export function getModelInfo(signal?: AbortSignal): Promise<ModelInfoResponse> {
  return request<ModelInfoResponse>('/api/v1/model-info', {
    signal,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  })
}

/** POST /api/v1/predict — multipart `file` field. */
export function predict(
  file: File,
  signal?: AbortSignal,
): Promise<PredictResponse> {
  const form = new FormData()
  form.append('file', file, file.name)

  return request<PredictResponse>('/api/v1/predict', {
    method: 'POST',
    body: form,
    signal,
    timeoutMs: PREDICT_TIMEOUT_MS,
  })
}

/** GET /api/v1/history */
export function getHistory(
  limit = 50,
  signal?: AbortSignal,
): Promise<HistoryListResponse> {
  const safeLimit = Math.min(200, Math.max(1, Math.trunc(limit)))
  return request<HistoryListResponse>(`/api/v1/history?limit=${safeLimit}`, {
    signal,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  })
}

/** GET /api/v1/history/{prediction_id} */
export function getHistoryItem(
  predictionId: string,
  signal?: AbortSignal,
): Promise<HistoryItem> {
  return request<HistoryItem>(
    `/api/v1/history/${encodeURIComponent(predictionId)}`,
    { signal, timeoutMs: DEFAULT_TIMEOUT_MS },
  )
}

/** DELETE /api/v1/history — removes rows and artifact files together. */
export function deleteHistory(
  signal?: AbortSignal,
): Promise<HistoryDeleteResponse> {
  return request<HistoryDeleteResponse>('/api/v1/history', {
    method: 'DELETE',
    signal,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  })
}
