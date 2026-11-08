import { useState } from 'react'

import { artifactUrl } from '../../services/api'
import type { HistoryItem, Severity } from '../../types/api'
import { diseaseLabel } from '../../utils/diseases'
import { formatScore, formatTimestamp } from '../../utils/format'
import { lesionAreaDisplay, severityDisplay } from '../../utils/measurements'
import { severityReasonMessage, warningMessage } from '../../utils/warnings'
import { ExternalLinkIcon, ImageIcon } from '../common/Icons'
import { StatusBadge } from '../common/StatusBadge'

const SEVERITY_BADGE: Record<Severity, string> = {
  Mild: 'border-accent-300 bg-accent-50 text-accent-800',
  Moderate: 'border-warn-300 bg-warn-50 text-warn-800',
  Severe: 'border-red-300 bg-red-50 text-red-800',
}

function HistoryThumbnail({ item }: { item: HistoryItem }) {
  const src = artifactUrl(item.artifacts.original_url)
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div
        className="flex h-12 w-12 items-center justify-center rounded-md border border-ink-200 bg-ink-50 text-ink-400"
        title={src ? 'Artifact unavailable or expired' : 'No image artifact stored'}
      >
        <ImageIcon className="h-5 w-5" />
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={`Temporary uploaded leaf for ${diseaseLabel(item.disease)}`}
      loading="lazy"
      className="h-12 w-12 rounded-md border border-ink-200 bg-ink-50 object-cover"
      onError={() => setFailed(true)}
    />
  )
}

function ArtifactLinks({ item }: { item: HistoryItem }) {
  const links = [
    { key: 'original', label: 'Image', url: item.artifacts.original_url },
    { key: 'leaf', label: 'Leaf', url: item.artifacts.leaf_mask_url },
    { key: 'lesion', label: 'Lesion', url: item.artifacts.lesion_mask_url },
  ]

  return (
    <div className="flex flex-wrap gap-1.5">
      {links.map(({ key, label, url }) => {
        const href = artifactUrl(url)
        if (!href) return null
        return (
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded border border-ink-200 bg-white px-1.5 py-0.5 text-[11px] font-medium text-ink-700 hover:border-accent-300 hover:text-accent-800"
            aria-label={`Open temporary ${label.toLowerCase()} artifact in a new tab`}
          >
            {label}
            <ExternalLinkIcon className="h-2.5 w-2.5" />
          </a>
        )
      })}
    </div>
  )
}

/**
 * History table. Only labelled results are stored by the backend; this table
 * additionally guards against a defensive `rejected` row.
 */
export function HistoryTable({ items }: { items: HistoryItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse text-sm">
        <caption className="sr-only">
          Temporary predictions from the current backend session
        </caption>
        <thead>
          <tr className="border-b border-ink-200 bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
            <th scope="col" className="px-4 py-3 font-semibold">
              Image
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Time
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Disease / status
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Severity
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Lesion area
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Best-vs-second margin
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Temporary artifacts
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const lesion = lesionAreaDisplay(
              item.lesion_area_percentage,
              item.lesion_reliable,
            )
            const severity = severityDisplay(
              item.severity,
              item.lesion_reliable && lesion.available,
              severityReasonMessage(item.severity_reason_code),
            )
            return (
              <tr
                key={item.prediction_id}
                className="border-b border-ink-100 align-top last:border-b-0 hover:bg-ink-50/60"
                data-testid="history-row"
              >
                <td className="px-4 py-3">
                  <HistoryThumbnail item={item} />
                </td>
                <td className="px-4 py-3 text-xs text-ink-600">
                  <div className="font-medium text-ink-800">{formatTimestamp(item.created_at)}</div>
                  <div className="mt-0.5 text-[11px] text-ink-500" title={item.expires_at}>
                    Expires {formatTimestamp(item.expires_at)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="font-semibold text-ink-900">
                    {item.status === 'rejected' ? 'Rejected upload' : diseaseLabel(item.disease)}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={item.status} />
                  </div>
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
                            <span className="font-mono text-[9px] uppercase text-ink-500">
                              {code}
                            </span>
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
                </td>
                <td className="px-4 py-3">
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
                <td className="px-4 py-3 text-xs text-ink-700">
                  <div className="font-medium tabular-nums">{lesion.text}</div>
                  {lesion.note ? (
                    <div className="mt-1 max-w-[170px] text-[11px] text-ink-500">{lesion.note}</div>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <div className="font-mono text-sm font-semibold tabular-nums text-ink-900">
                    {formatScore(item.margin)}
                  </div>
                  <div className="text-[11px] text-ink-500">not a probability</div>
                </td>
                <td className="px-4 py-3">
                  <ArtifactLinks item={item} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
