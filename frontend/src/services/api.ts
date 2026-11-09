import type {
  ErrorEnvelope,
  HealthResponse,
  HistoryDeleteResponse,
  HistoryItem,
  HistoryListResponse,
  ModelInfoResponse,
  PredictResponse,
} from '../types/api'

export const DEV_API_BASE_URL = 'http://localhost:8000'

export interface ApiBaseUrlResolution {
  baseUrl: string
  /** Set when the deployment cannot possibly reach a backend; shown instead of crashing. */
  configError: string | null
}

function isLoopbackHostname(hostname: string): boolean {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase()
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host.endsWith('.localhost')
}

/**
 * Resolve the API origin once at build time.
 *
 * A missing variable is tolerated in development (localhost fallback) but is a
 * configuration error in a deployed build. Invalid values never throw during
 * module import — that would blank the whole dashboard — instead every request
 * fails with a readable configuration message.
 */
export function resolveApiBaseUrl(
  configured: string | undefined,
  {
    dev,
    pageHostname = null,
  }: { dev: boolean; pageHostname?: string | null },
): ApiBaseUrlResolution {
  const raw = configured?.trim()
  if (!raw) {
    return {
      baseUrl: DEV_API_BASE_URL,
      configError: dev
        ? null
        : 'This dashboard was built without VITE_API_BASE_URL, so it has no backend address. Set VITE_API_BASE_URL to the Render service origin (for example https://dhanyadrishti-api.onrender.com) and redeploy.',
    }
  }

  const candidate = raw.replace(/\/+$/, '')
  if (!/^https?:\/\/[^\s/]+$/i.test(candidate)) {
    return {
      baseUrl: DEV_API_BASE_URL,
      configError: `VITE_API_BASE_URL must be a bare http(s) origin such as https://dhanyadrishti-api.onrender.com (received “${raw}”). Do not include /api/v1 or a trailing path.`,
    }
  }

  try {
    const parsed = new URL(candidate)
    if (
      (parsed.pathname && parsed.pathname !== '/') ||
      parsed.search.length > 0 ||
      parsed.hash.length > 0
    ) {
      return {
        baseUrl: parsed.origin,
        configError: `VITE_API_BASE_URL must be an origin only; remove the path, query or hash from “${raw}”.`,
      }
    }

    if (
      !dev &&
      pageHostname &&
      !isLoopbackHostname(pageHostname) &&
      isLoopbackHostname(parsed.hostname)
    ) {
      return {
        baseUrl: parsed.origin,
        configError: `This deployment points VITE_API_BASE_URL at ${parsed.origin}, which is this visitor's own computer. Use the public Render service URL and redeploy.`,
      }
    }

    return { baseUrl: parsed.origin, configError: null }
  } catch {
    return {
      baseUrl: DEV_API_BASE_URL,
      configError: `VITE_API_BASE_URL is not a valid URL (received “${raw}”).`,
    }
  }
}

const resolvedApiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, {
  dev: import.meta.env.DEV,
  pageHostname: typeof window === 'undefined' ? null : window.location.hostname,
})

/** Backend base URL comes from VITE_API_BASE_URL (PRD §21). */
export const API_BASE_URL = resolvedApiBaseUrl.baseUrl
/** Non-null when the deployed frontend has no usable backend address. */
export const API_CONFIG_ERROR = resolvedApiBaseUrl.configError

export const DEFAULT_UPLOAD_LIMIT_MB = 10

const HEALTH_TIMEOUT_MS = 6_000
const DEFAULT_TIMEOUT_MS = 20_000
/** CPU inference can be slow on first use, so /predict gets a wider budget. */
const PREDICT_TIMEOUT_MS = 90_000

export type ApiErrorKind =
  | 'http'
  | 'network'
  | 'timeout'
  | 'aborted'
  | 'invalid-response'
  | 'config'

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
  cache?: RequestCache
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
  if (API_CONFIG_ERROR) {
    throw new ApiError(API_CONFIG_ERROR, { kind: 'config' })
  }

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
        cache: options.cache,
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
  // `no-store` makes every health call a real request instead of a cached read:
  // the same call doubles as the keep-alive ping that stops a free-tier backend
  // from spinning down while the dashboard is open.
  return request<HealthResponse>('/api/v1/health', {
    signal,
    timeoutMs: HEALTH_TIMEOUT_MS,
    cache: 'no-store',
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
