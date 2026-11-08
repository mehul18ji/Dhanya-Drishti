import type { PredictionResponse, Severity } from '../../types/api'
import {
  GENERAL_DISCLAIMER,
  HEALTHY_CAVEAT,
  SEVERITY_DISCLAIMER,
  UNCERTAIN_NOTICE,
} from '../../utils/disclaimers'
import { diseaseLabel } from '../../utils/diseases'
import { formatDecimal, formatDuration, formatTimestamp, truncateId } from '../../utils/format'
import { lesionAreaDisplay, severityDisplay } from '../../utils/measurements'
import { severityReasonMessage } from '../../utils/warnings'
import { Callout } from '../common/Callout'
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
  ShieldIcon,
} from '../common/Icons'
import { StatusBadge } from '../common/StatusBadge'
import { MissingFeaturesCard, QualityWarningCard } from './QualityWarningCard'
import { ScorePanel } from './ScorePanel'
import { SegmentationPreviewPanel } from './SegmentationPreviewPanel'

const SEVERITY_STYLES: Record<
  Severity,
  { badge: string; Icon: typeof CheckCircleIcon }
> = {
  Mild: {
    badge: 'border-accent-300 bg-accent-50 text-accent-800',
    Icon: CheckCircleIcon,
  },
  Moderate: {
    badge: 'border-warn-300 bg-warn-50 text-warn-800',
    Icon: AlertTriangleIcon,
  },
  Severe: {
    badge: 'border-red-300 bg-red-50 text-red-800',
    Icon: AlertTriangleIcon,
  },
}

function SeverityCard({
  prediction,
  lesionAvailable,
}: {
  prediction: PredictionResponse
  lesionAvailable: boolean
}) {
  const display = severityDisplay(
    prediction.severity,
    prediction.lesion_reliable && lesionAvailable,
    severityReasonMessage(prediction.severity_reason_code),
  )
  const styles = display.severity ? SEVERITY_STYLES[display.severity] : null
  const Icon = styles?.Icon ?? AlertTriangleIcon

  return (
    <div className="rounded-lg border border-ink-200 bg-white p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        Experimental severity
      </p>
      <div className="mt-2">
        {display.available && styles ? (
          <span className={`badge ${styles.badge}`} data-testid="severity-badge">
            <Icon className="h-3.5 w-3.5" />
            {display.text}
          </span>
        ) : (
          <span className="badge border-ink-300 bg-ink-100 text-ink-700" data-testid="severity-badge">
            <AlertTriangleIcon className="h-3.5 w-3.5" />
            {display.text}
          </span>
        )}
      </div>
      {display.note ? (
        <p className="mt-2 text-xs leading-relaxed text-ink-600" data-testid="severity-note">
          {display.note}
        </p>
      ) : (
        <p className="mt-2 text-xs leading-relaxed text-ink-600">{prediction.severity_note}</p>
      )}
      <p
        className="mt-2 border-t border-ink-100 pt-2 text-[11px] leading-relaxed text-ink-500"
        data-testid="severity-disclaimer"
      >
        {prediction.severity_disclaimer || SEVERITY_DISCLAIMER}
      </p>
    </div>
  )
}

export function PredictionResultCard({
  prediction,
  onAnalyzeAnother,
}: {
  prediction: PredictionResponse
  onAnalyzeAnother?: () => void
}) {
  const uncertain = prediction.status === 'uncertain'
  const lesion = lesionAreaDisplay(
    prediction.lesion_area_percentage,
    prediction.lesion_reliable,
  )
  const stageEntries = Object.entries(prediction.stage_ms)

  return (
    <article
      className={[
        'card overflow-hidden border-2',
        uncertain ? 'border-warn-300' : 'border-ink-200',
      ].join(' ')}
      data-testid="prediction-result"
      data-status={prediction.status}
      aria-labelledby="prediction-result-heading"
    >
      <div
        className={[
          'flex flex-wrap items-start justify-between gap-3 border-b px-5 py-4',
          uncertain ? 'border-warn-200 bg-warn-50/70' : 'border-ink-200 bg-white',
        ].join(' ')}
      >
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-500">
            Analysis result
          </p>
          <h2
            id="prediction-result-heading"
            className="mt-1 text-2xl font-semibold tracking-tight text-ink-900"
          >
            {diseaseLabel(prediction.disease)}
          </h2>
          <p className="mt-1 text-sm text-ink-600">
            {uncertain
              ? 'Unconfirmed pattern — this is not a diagnosis.'
              : 'Class selected from the three supported rice-leaf diseases.'}
          </p>
        </div>
        <StatusBadge status={prediction.status} />
      </div>

      <div className="space-y-5 p-5">
        {uncertain ? (
          <Callout tone="warning" title="Uncertain result — treat the label as unconfirmed">
            <p>{UNCERTAIN_NOTICE}</p>
            <p className="mt-2 text-xs">
              This safeguard is not a healthy-leaf classifier. It means the image, quality checks,
              lesion measurement or features did not support a confirmed prediction.
            </p>
          </Callout>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <SeverityCard prediction={prediction} lesionAvailable={lesion.available} />
          <div className="rounded-lg border border-ink-200 bg-white p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
              Lesion area of the detected leaf
            </p>
            <p className="mt-2 text-xl font-semibold tabular-nums text-ink-900">
              {lesion.text}
            </p>
            {lesion.note ? (
              <p className="mt-1 text-xs leading-relaxed text-ink-600">{lesion.note}</p>
            ) : (
              <p className="mt-1 text-xs leading-relaxed text-ink-600">
                Visible lesion area as a share of the segmented leaf. It is a measurement, not a
                trained severity grade.
              </p>
            )}
            {!lesion.available ? (
              <p className="mt-2 text-[11px] font-medium text-warn-800">
                Not converted to 0% and not assigned a severity bucket.
              </p>
            ) : null}
          </div>
        </div>

        <Callout tone="neutral" title="Supported labels only" className="block">
          <p>{HEALTHY_CAVEAT}</p>
        </Callout>

        <ScorePanel
          scores={prediction.decision_scores}
          ranking={prediction.ranking}
          margin={prediction.margin}
          scoreNote={prediction.score_note}
        />

        <QualityWarningCard codes={prediction.warnings} />
        <MissingFeaturesCard features={prediction.missing_features} />

        {prediction.rejections.length > 0 ? (
          <Callout tone="danger" title="Pipeline rejection codes">
            <ul className="list-disc pl-5">
              {prediction.rejections.map((code) => (
                <li key={code} className="font-mono text-xs">
                  {code}
                </li>
              ))}
            </ul>
          </Callout>
        ) : null}

        <SegmentationPreviewPanel artifacts={prediction.artifacts} />

        <div className="grid gap-3 rounded-lg border border-ink-200 bg-ink-50 p-4 text-xs text-ink-600 sm:grid-cols-3">
          <div>
            <p className="font-semibold text-ink-800">Model</p>
            <p className="mt-0.5">
              {prediction.model_name} · {prediction.model_version}
            </p>
          </div>
          <div>
            <p className="font-semibold text-ink-800">Feature set</p>
            <p className="mt-0.5">{prediction.feature_set_version}</p>
          </div>
          <div>
            <p className="font-semibold text-ink-800">Created</p>
            <p className="mt-0.5 inline-flex items-center gap-1">
              <ClockIcon className="h-3.5 w-3.5" />
              {formatTimestamp(prediction.created_at)}
            </p>
          </div>
        </div>

        <details className="rounded-lg border border-ink-200 bg-white px-4 py-3 text-xs text-ink-600">
          <summary className="cursor-pointer font-semibold text-ink-800">
            Prediction provenance and timings
          </summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="font-medium text-ink-500">Prediction ID</dt>
              <dd className="font-mono text-[11px]" title={prediction.prediction_id}>
                {truncateId(prediction.prediction_id)}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Segmentation config</dt>
              <dd>{prediction.segmentation_config_version}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Quality config</dt>
              <dd>{prediction.quality_config_version}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Severity config</dt>
              <dd>
                {prediction.severity_config_version} ·{' '}
                <span className="font-mono text-[10px]">
                  {prediction.severity_config_sha256.slice(0, 12)}…
                </span>
              </dd>
            </div>
            {stageEntries.length > 0 ? (
              <div className="sm:col-span-2">
                <dt className="font-medium text-ink-500">Stage timings</dt>
                <dd className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                  {stageEntries.map(([stage, milliseconds]) => (
                    <span key={stage}>
                      <span className="font-mono text-[10px] uppercase text-ink-500">{stage}</span>{' '}
                      {formatDuration(milliseconds)}
                    </span>
                  ))}
                </dd>
              </div>
            ) : null}
          </dl>
          <p className="mt-3 text-[11px] text-ink-500">
            Score kind: <span className="font-mono">{prediction.score_kind}</span>. Reliability
            flags and warnings are shown above; they are never hidden.
          </p>
        </details>

        <div className="rounded-lg border border-ink-200 bg-ink-50 p-4 text-[11px] leading-relaxed text-ink-600">
          <p className="flex items-start gap-2">
            <ShieldIcon className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
            <span>{GENERAL_DISCLAIMER}</span>
          </p>
          <p className="mt-2">
            Best-vs-second margin: {formatDecimal(prediction.margin, 3)}. Not a probability and not
            a confidence percentage.
          </p>
        </div>

        {onAnalyzeAnother ? (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onAnalyzeAnother}
              className="rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-800"
            >
              Analyze another image
            </button>
            <p className="text-xs text-ink-500">
              This result remains in temporary history until it expires or history is cleared.
            </p>
          </div>
        ) : null}
      </div>
    </article>
  )
}
