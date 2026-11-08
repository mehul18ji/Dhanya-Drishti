import type { RejectedResponse } from '../../types/api'
import { GENERAL_DISCLAIMER } from '../../utils/disclaimers'
import { rejectionGuidance } from '../../utils/warnings'
import { Callout } from '../common/Callout'
import { XCircleIcon } from '../common/Icons'

/**
 * HTTP 200 `status: "rejected"` card. Visually distinct from a prediction: no
 * disease label, no scores, no severity and no history record.
 */
export function RejectedResultCard({
  rejection,
  onChooseAnother,
}: {
  rejection: RejectedResponse
  onChooseAnother?: () => void
}) {
  return (
    <article
      className="card overflow-hidden border-2 border-ink-300"
      data-testid="rejected-result"
      aria-labelledby="rejected-result-heading"
    >
      <div className="flex items-start gap-3 border-b border-ink-200 bg-ink-100 px-5 py-4">
        <XCircleIcon className="mt-0.5 h-6 w-6 shrink-0 text-ink-600" />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-500">
            Image rejected — no prediction
          </p>
          <h2
            id="rejected-result-heading"
            className="mt-1 text-xl font-semibold tracking-tight text-ink-900"
          >
            This image could not be analysed
          </h2>
        </div>
      </div>

      <div className="space-y-4 p-5">
        <Callout tone="neutral" title="Rejection reason">
          <p>{rejection.message}</p>
          <p className="mt-2 font-mono text-[11px] uppercase tracking-wide text-ink-500">
            {rejection.reason_code}
          </p>
        </Callout>

        <div className="rounded-lg border border-ink-200 bg-white p-4 text-sm text-ink-700">
          <p className="font-semibold text-ink-900">What to try</p>
          <p className="mt-1">{rejectionGuidance(rejection.reason_code)}</p>
        </div>

        <ul className="list-disc space-y-1 pl-5 text-xs text-ink-600">
          <li>No disease label was assigned.</li>
          <li>No decision scores, severity or diagnostic artifacts were produced.</li>
          <li>This upload was not added to temporary prediction history.</li>
        </ul>

        <p className="border-t border-ink-200 pt-3 text-[11px] leading-relaxed text-ink-500">
          {GENERAL_DISCLAIMER}
        </p>

        {onChooseAnother ? (
          <button
            type="button"
            onClick={onChooseAnother}
            className="rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-800"
          >
            Choose another image
          </button>
        ) : null}
      </div>
    </article>
  )
}
