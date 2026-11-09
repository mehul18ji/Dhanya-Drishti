import { API_BASE_URL, ApiError, DEFAULT_UPLOAD_LIMIT_MB } from '../services/api'

export type ErrorContext = 'predict' | 'history' | 'model' | 'health'

export interface FriendlyError {
  title: string
  message: string
  /** Safe backend explanation, when it adds information. */
  detail?: string
  tone: 'danger' | 'warning'
  retryable: boolean
  code?: string | null
}

function withDetail(
  friendly: FriendlyError,
  error: ApiError,
  fallbackTitle: string,
): FriendlyError {
  const backendMessage = error.message?.trim()
  const generic =
    backendMessage.length === 0 ||
    /^the analysis service returned http/i.test(backendMessage) ||
    backendMessage === fallbackTitle
  return {
    ...friendly,
    detail: generic ? undefined : backendMessage,
    code: friendly.code ?? error.reasonCode,
  }
}

/**
 * Map a client-side failure onto human-readable guidance.
 *
 * Upload-level errors (413/415/422), model-unavailable (503) and generic server
 * failures stay distinct — a rejected image is a separate 200 response handled by
 * `RejectedResultCard`, never by this function.
 */
export function describeApiError(
  error: unknown,
  context: ErrorContext = 'predict',
): FriendlyError {
  if (!(error instanceof ApiError)) {
    return {
      title: 'Unexpected error',
      message:
        'Something went wrong while contacting the analysis service. Retry, then check the backend log if the problem persists.',
      tone: 'danger',
      retryable: true,
    }
  }

  if (error.kind === 'aborted') {
    return {
      title: 'Request cancelled',
      message: 'The request was cancelled before a result was received.',
      tone: 'warning',
      retryable: true,
      code: error.reasonCode,
    }
  }

  if (error.kind === 'config') {
    return {
      title: 'Analysis service is not configured',
      message: error.message,
      tone: 'danger',
      retryable: false,
      code: error.reasonCode,
    }
  }

  if (error.kind === 'timeout') {
    return {
      title: 'Analysis service is slow to respond',
      message:
        'The backend may be waking from sleep or CPU inference is taking longer than expected. This page retries automatically; if it persists, press Retry or check the service log.',
      tone: 'warning',
      retryable: true,
      code: error.reasonCode,
    }
  }

  if (error.kind === 'network') {
    return {
      title: 'Starting analysis service…',
      message: `Could not reach the analysis service at ${API_BASE_URL}. A free-hosted backend can take up to a minute to wake from sleep. This page retries automatically; if the problem persists, check that the Render URL and CORS origin match this deployment.`,
      tone: 'warning',
      retryable: true,
      code: error.reasonCode,
    }
  }

  if (error.kind === 'invalid-response') {
    return {
      title: 'Unexpected response',
      message:
        'The analysis service answered with a body this dashboard could not read. Check that the frontend and backend versions match.',
      tone: 'danger',
      retryable: true,
      code: error.reasonCode,
    }
  }

  const status = error.status

  if (status === 413 || error.reasonCode === 'FILE_TOO_LARGE') {
    return withDetail(
      {
        title: 'File too large',
        message: `The upload exceeds the configured size limit (${DEFAULT_UPLOAD_LIMIT_MB} MB by default). Choose a smaller image.`,
        tone: 'danger',
        retryable: false,
        code: error.reasonCode,
      },
      error,
      'File too large',
    )
  }

  if (status === 415 || error.reasonCode === 'UNSUPPORTED_FILE_TYPE') {
    return withDetail(
      {
        title: 'Unsupported file type',
        message: 'Upload a JPG, JPEG, PNG or WEBP photograph of one rice leaf.',
        tone: 'danger',
        retryable: false,
        code: error.reasonCode,
      },
      error,
      'Unsupported file type',
    )
  }

  if (status === 422 || error.reasonCode === 'INVALID_UPLOAD') {
    if (error.reasonCode === 'IMAGE_TOO_SMALL') {
      return withDetail(
        {
          title: 'Image too small',
          message:
            'The image is below the minimum dimensions for reliable analysis. Upload a higher-resolution photograph taken closer to the leaf.',
          tone: 'danger',
          retryable: false,
          code: error.reasonCode,
        },
        error,
        'Image too small',
      )
    }
    return withDetail(
      {
        title: 'Image could not be read',
        message:
          'The file is empty, corrupt, or not a decodable image. Try re-exporting it as JPG or PNG.',
        tone: 'danger',
        retryable: false,
        code: error.reasonCode,
      },
      error,
      'Image could not be read',
    )
  }

  if (status === 503 && error.reasonCode === 'MODEL_NOT_LOADED') {
    return withDetail(
      {
        title: 'Analysis service is starting…',
        message:
          'The backend is online but the production model is not available yet. Wait a few seconds, then retry. If it persists, check the backend startup log.',
        tone: 'warning',
        retryable: true,
        code: error.reasonCode,
      },
      error,
      'Analysis service is starting…',
    )
  }

  // A sleeping/restarting free instance or proxy often answers 502/503/504 with
  // an HTML page rather than the API's JSON error envelope.
  if (status === 502 || status === 503 || status === 504) {
    return {
      title: 'Analysis service is waking up…',
      message:
        'The hosted backend is restarting or waking from sleep. This is normal on a free instance and usually clears within a minute. The page retries automatically; press Retry if you do not want to wait.',
      tone: 'warning',
      retryable: true,
      code: error.reasonCode,
    }
  }

  if (status === 429) {
    return {
      title: 'Too many requests',
      message:
        'The analysis service is temporarily rate-limited. Wait a few seconds and retry. No upload was analysed and nothing was saved to history.',
      tone: 'warning',
      retryable: true,
      code: error.reasonCode,
    }
  }

  if (status === 404) {
    if (context === 'history') {
      return {
        title: 'Prediction not found',
        message:
          'This temporary record has expired or was removed. History is cleared when the backend restarts.',
        tone: 'warning',
        retryable: false,
        code: error.reasonCode,
      }
    }
    return withDetail(
      {
        title: 'Backend endpoint not found',
        message:
          'The analysis service answered, but not at the expected API path. Check that VITE_API_BASE_URL points to the backend origin (not the Vercel frontend) and redeploy.',
        tone: 'danger',
        retryable: false,
        code: error.reasonCode,
      },
      error,
      'Not found',
    )
  }

  if (status !== null && status >= 500) {
    return withDetail(
      {
        title: 'Analysis failed',
        message:
          'The backend could not complete this request. Retry once; if it keeps failing, check the backend log.',
        tone: 'danger',
        retryable: true,
        code: error.reasonCode,
      },
      error,
      'Analysis failed',
    )
  }

  return withDetail(
    {
      title:
        context === 'model'
          ? 'Model information unavailable'
          : context === 'history'
            ? 'History unavailable'
            : 'Request failed',
      message:
        'The analysis service returned an error. Retry, then check that the frontend and backend versions match.',
      tone: 'danger',
      retryable: true,
      code: error.reasonCode,
    },
    error,
    'Request failed',
  )
}

export function isAbortError(error: unknown): boolean {
  return error instanceof ApiError && error.kind === 'aborted'
}
