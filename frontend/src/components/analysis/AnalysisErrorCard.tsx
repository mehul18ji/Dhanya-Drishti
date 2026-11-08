import type { FriendlyError } from '../../utils/errors'
import { ErrorNotice } from '../common/ErrorNotice'

/**
 * Upload-level / transport error. This is explicitly not a prediction and never
 * creates a history record.
 */
export function AnalysisErrorCard({
  error,
  onRetry,
  retrying = false,
}: {
  error: FriendlyError
  onRetry?: () => void
  retrying?: boolean
}) {
  const border = error.tone === 'warning' ? 'border-warn-300' : 'border-red-200'
  return (
    <section
      className={`card border-2 ${border} p-5`}
      aria-labelledby="analysis-error-heading"
      data-testid="analysis-error"
    >
      <h2 id="analysis-error-heading" className="text-lg font-semibold text-ink-900">
        Analysis error
      </h2>
      <p className="mt-1 text-sm text-ink-600">
        The upload did not produce a prediction. This is an upload or service error, not a disease
        result.
      </p>
      <div className="mt-4">
        <ErrorNotice error={error} onRetry={onRetry} retrying={retrying} />
      </div>
      <p className="mt-4 border-t border-ink-200 pt-3 text-xs text-ink-500">
        Upload-level failures (such as 413 file-too-large, 415 unsupported type, 422 unreadable
        image) and model-unavailable 503 responses are never saved as history records. A rejected
        analysis returned with HTTP 200 is also not saved.
      </p>
    </section>
  )
}
