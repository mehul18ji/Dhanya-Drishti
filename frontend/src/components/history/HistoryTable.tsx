import { useState } from 'react'

import { artifactUrl } from '../../services/api'
import type { HistoryItem, Severity } from '../../types/api'
import { diseaseLabel } from '../../utils/diseases'
import { formatScore, formatTimestamp } from '../../utils/format'
import { lesionAreaDisplay, severityDisplay } from '../../utils/measurements'
import { severityReasonMessage, warningMessage } from '../../utils/warnings'
import { ArtifactPreview, type PreviewableArtifact } from '../common/ArtifactPreview'
import { ImageIcon, MaximizeIcon } from '../common/Icons'
import { StatusBadge } from '../common/StatusBadge'

const SEVERITY_BADGE: Record<Severity, string> = {
  Mild: 'border-accent-300 bg-accent-50 text-accent-800',
  Moderate: 'border-warn-300 bg-warn-50 text-warn-800',
  Severe: 'border-red-300 bg-red-50 text-red-800',
}

const ARTIFACT_LINKS = [
  { key: 'original_url', label: 'Image' },
  { key: 'leaf_mask_url', label: 'Leaf mask' },
  { key: 'lesion_mask_url', label: 'Lesion mask' },
] as const

type ArtifactKey = (typeof ARTIFACT_LINKS)[number]['key']
type HistoryArtifact = PreviewableArtifact & { key: ArtifactKey }

function itemArtifacts(item: HistoryItem): HistoryArtifact[] {
  return ARTIFACT_LINKS.flatMap(({ key, label }) => {
    const src = artifactUrl(item.artifacts[key])
    if (!src) return []
    return [
      {
        key,
        src,
        label,
        caption: `Temporary ${label.toLowerCase()} artifact for ${diseaseLabel(item.disease)}.`,
      } satisfies HistoryArtifact,
    ]
  })
}

function HistoryThumbnail({
  item,
  onPreview,
  large = false,
}: {
  item: HistoryItem
  onPreview: () => void
  large?: boolean
}) {
  const src = artifactUrl(item.artifacts.original_url)
  const [failed, setFailed] = useState(false)
  const size = large ? 'h-16 w-16' : 'h-12 w-12'

  if (!src || failed) {
    return (
      <div
        className={`flex ${size} items-center justify-center rounded-lg border border-ink-200 bg-ink-50 text-ink-400`}
        title={src ? 'Artifact unavailable or expired' : 'No image artifact stored'}
      >
        <ImageIcon className="h-5 w-5" />
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={onPreview}
      aria-label="Preview temporary uploaded leaf image"
      className={`group relative ${size} shrink-0 overflow-hidden rounded-lg border border-ink-200 bg-ink-50 focus-visible:ring-2 focus-visible:ring-accent-500`}
    >
      <img
        src={src}
        alt={`Temporary uploaded leaf for ${diseaseLabel(item.disease)}`}
        loading="lazy"
        decoding="async"
        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        onError={() => setFailed(true)}
      />
      <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-ink-950/0 text-white opacity-0 transition group-hover:bg-ink-950/35 group-hover:opacity-100">
        <MaximizeIcon className="h-4 w-4" />
      </span>
    </button>
  )
}

function WarningDetails({ item }: { item: HistoryItem }) {
  return (
    <>
      {item.warnings.length > 0 ? (
        <details className="mt-1 max-w-[280px] text-[11px] text-warn-800">
          <summary className="cursor-pointer font-medium">
            {item.warnings.length} quality warning
            {item.warnings.length === 1 ? '' : 's'} · details
          </summary>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            {item.warnings.map((code) => (
              <li key={code}>
                {warningMessage(code)}{' '}
                <span className="font-mono text-[9px] uppercase text-ink-500">{code}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {item.missing_features.length > 0 ? (
        <details className="mt-1 max-w-[280px] text-[11px] text-ink-600">
          <summary className="cursor-pointer font-medium">
            {item.missing_features.length} missing feature
            {item.missing_features.length === 1 ? '' : 's'} · details
          </summary>
          <ul className="mt-1 flex flex-wrap gap-1">
            {item.missing_features.map((feature) => (
              <li
                key={feature}
                className="rounded border border-ink-200 bg-white px-1 py-0.5 font-mono text-[10px]"
              >
                {feature}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  )
}

function ArtifactButtons({
  artifacts,
  onOpen,
}: {
  artifacts: HistoryArtifact[]
  onOpen: (key: ArtifactKey) => void
}) {
  if (artifacts.length === 0) {
    return <span className="text-[11px] text-ink-400">No artifacts</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {artifacts.map((artifact) => (
        <button
          key={artifact.key}
          type="button"
          onClick={() => onOpen(artifact.key)}
          aria-label={`Preview temporary ${artifact.label.toLowerCase()} artifact`}
          className="inline-flex min-h-[30px] items-center gap-1 rounded-md border border-ink-200 bg-white px-2 py-1 text-[11px] font-medium text-ink-700 transition hover:border-accent-300 hover:text-accent-800"
        >
          {artifact.label}
          <MaximizeIcon className="h-2.5 w-2.5" />
        </button>
      ))}
    </div>
  )
}

function severityFor(item: HistoryItem, lesionAvailable: boolean) {
  return severityDisplay(
    item.severity,
    item.lesion_reliable && lesionAvailable,
    severityReasonMessage(item.severity_reason_code),
  )
}

function HistoryCard({
  item,
  onPreview,
}: {
  item: HistoryItem
  onPreview: (key: ArtifactKey) => void
}) {
  const lesion = lesionAreaDisplay(item.lesion_area_percentage, item.lesion_reliable)
  const severity = severityFor(item, lesion.available)
  const artifacts = itemArtifacts(item)

  return (
    <article className="p-4" data-testid="history-card">
      <div className="flex gap-3">
        <HistoryThumbnail item={item} large onPreview={() => onPreview('original_url')} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-semibold text-ink-900">
                {item.status === 'rejected' ? 'Rejected upload' : diseaseLabel(item.disease)}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-500">
                {formatTimestamp(item.created_at)}
              </p>
            </div>
            <StatusBadge status={item.status} />
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
            <div>
              <dt className="font-medium text-ink-500">Severity</dt>
              <dd className="mt-0.5">
                {severity.available && item.severity ? (
                  <span className={`badge ${SEVERITY_BADGE[item.severity]}`}>{severity.text}</span>
                ) : (
                  <span className="badge border-ink-300 bg-ink-100 text-ink-700">
                    {severity.text}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Lesion area</dt>
              <dd className="mt-0.5 font-medium tabular-nums text-ink-800">{lesion.text}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Best-vs-second margin</dt>
              <dd className="mt-0.5 font-mono font-semibold tabular-nums text-ink-900">
                {formatScore(item.margin)}
              </dd>
              <dd className="text-[10px] text-ink-500">not a probability</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-500">Expires</dt>
              <dd className="mt-0.5 text-ink-700">{formatTimestamp(item.expires_at)}</dd>
            </div>
          </dl>

          <WarningDetails item={item} />
          <div className="mt-2">
            <ArtifactButtons artifacts={artifacts} onOpen={onPreview} />
          </div>
        </div>
      </div>
    </article>
  )
}

/**
 * History table. Only labelled results are stored by the backend; this table
 * additionally guards against a defensive `rejected` row. Phones get cards,
 * wider screens get the full table.
 */
export function HistoryTable({ items }: { items: HistoryItem[] }) {
  const [preview, setPreview] = useState<{
    items: PreviewableArtifact[]
    index: number
  } | null>(null)

  const openPreview = (item: HistoryItem, key: ArtifactKey) => {
    const artifacts = itemArtifacts(item)
    if (artifacts.length === 0) return
    const index = Math.max(
      0,
      artifacts.findIndex((artifact) => artifact.key === key),
    )
    setPreview({ items: artifacts, index })
  }

  return (
    <div>
      <div className="divide-y divide-ink-100 md:hidden">
        {items.map((item) => (
          <HistoryCard
            key={item.prediction_id}
            item={item}
            onPreview={(key) => openPreview(item, key)}
          />
        ))}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <caption className="sr-only">
            Temporary predictions from the current backend session
          </caption>
          <thead>
            <tr className="border-b border-ink-200 bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Image
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Time
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Disease / status
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Severity
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Lesion area
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Best-vs-second margin
              </th>
              <th scope="col" className="px-3 py-3 font-semibold sm:px-4">
                Temporary artifacts
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const lesion = lesionAreaDisplay(item.lesion_area_percentage, item.lesion_reliable)
              const severity = severityFor(item, lesion.available)
              const artifacts = itemArtifacts(item)
              return (
                <tr
                  key={item.prediction_id}
                  className="border-b border-ink-100 align-top last:border-b-0 hover:bg-ink-50/60"
                  data-testid="history-row"
                >
                  <td className="px-3 py-3 sm:px-4">
                    <HistoryThumbnail
                      item={item}
                      onPreview={() => openPreview(item, 'original_url')}
                    />
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-600 sm:px-4">
                    <div className="font-medium text-ink-800">
                      {formatTimestamp(item.created_at)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-ink-500" title={item.expires_at}>
                      Expires {formatTimestamp(item.expires_at)}
                    </div>
                  </td>
                  <td className="px-3 py-3 sm:px-4">
                    <div className="font-semibold text-ink-900">
                      {item.status === 'rejected'
                        ? 'Rejected upload'
                        : diseaseLabel(item.disease)}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={item.status} />
                    </div>
                    <WarningDetails item={item} />
                  </td>
                  <td className="px-3 py-3 sm:px-4">
                    {severity.available && item.severity ? (
                      <span className={`badge ${SEVERITY_BADGE[item.severity]}`}>
                        {severity.text}
                      </span>
                    ) : (
                      <div>
                        <span className="badge border-ink-300 bg-ink-100 text-ink-700">
                          {severity.text}
                        </span>
                        {severity.note ? (
                          <p className="mt-1 max-w-[180px] text-[11px] text-ink-500">
                            {severity.note}
                          </p>
                        ) : null}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs text-ink-700 sm:px-4">
                    <div className="font-medium tabular-nums">{lesion.text}</div>
                    {lesion.note ? (
                      <div className="mt-1 max-w-[170px] text-[11px] text-ink-500">
                        {lesion.note}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 sm:px-4">
                    <div className="font-mono text-sm font-semibold tabular-nums text-ink-900">
                      {formatScore(item.margin)}
                    </div>
                    <div className="text-[11px] text-ink-500">not a probability</div>
                  </td>
                  <td className="px-3 py-3 sm:px-4">
                    <ArtifactButtons
                      artifacts={artifacts}
                      onOpen={(key) => openPreview(item, key)}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <ArtifactPreview
        items={preview?.items ?? []}
        index={preview?.index ?? null}
        onIndexChange={(index) =>
          setPreview((current) => (current ? { ...current, index } : current))
        }
        onClose={() => setPreview(null)}
      />
    </div>
  )
}
