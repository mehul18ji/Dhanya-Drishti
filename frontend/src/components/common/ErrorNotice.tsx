import type { FriendlyError } from '../../utils/errors'
import { Callout } from './Callout'
import { RefreshIcon } from './Icons'
import { Spinner } from './Spinner'

export function ErrorNotice({
  error,
  onRetry,
  retryLabel = 'Retry',
  retrying = false,
  autoRetrying = false,
}: {
  error: FriendlyError
  onRetry?: () => void
  retryLabel?: string
  retrying?: boolean
  /** A retry is already scheduled; tell the user no action is required. */
  autoRetrying?: boolean
}) {
  return (
    <div data-testid="error-notice">
      <Callout
        tone={error.tone}
        title={error.title}
        role="alert"
        className="flex-col sm:flex-row sm:items-start"
      >
        <p>{error.message}</p>
        {error.detail ? (
          <p className="mt-1 text-xs text-ink-600">
            <span className="font-medium">Backend detail:</span> {error.detail}
          </p>
        ) : null}
        {error.code ? (
          <p className="mt-1 font-mono text-[11px] uppercase tracking-wide text-ink-500">
            Code: {error.code}
          </p>
        ) : null}
        {autoRetrying ? (
          <p className="mt-2 text-xs text-ink-600" data-testid="auto-retry-hint">
            Retrying automatically — no action needed. The hosted backend may be waking from sleep.
          </p>
        ) : null}
        {onRetry && error.retryable ? (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="mt-3 inline-flex items-center gap-2 rounded-lg border border-ink-300 bg-white px-3 py-1.5 text-xs font-semibold text-ink-800 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {retrying ? <Spinner /> : <RefreshIcon className="h-3.5 w-3.5" />}
            {retryLabel}
          </button>
        ) : null}
      </Callout>
    </div>
  )
}
