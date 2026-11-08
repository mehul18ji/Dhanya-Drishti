import { useState } from 'react'

import { artifactUrl } from '../../services/api'
import type { ArtifactLinks } from '../../types/api'
import { ExternalLinkIcon, ImageIcon } from '../common/Icons'

interface Artifact {
  key: keyof ArtifactLinks
  label: string
  caption: string
}

const ARTIFACTS: Artifact[] = [
  {
    key: 'original_url',
    label: 'Oriented upload',
    caption: 'The decoded upload after EXIF orientation correction.',
  },
  {
    key: 'leaf_mask_url',
    label: 'Leaf mask',
    caption: 'The primary leaf region selected for analysis.',
  },
  {
    key: 'lesion_mask_url',
    label: 'Lesion mask',
    caption: 'Disease regions detected inside the leaf.',
  },
]

function ArtifactThumbnail({
  src,
  label,
  caption,
}: {
  src: string | null
  label: string
  caption: string
}) {
  const [failed, setFailed] = useState(false)
  if (!src) return null

  return (
    <figure className="min-w-0">
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="group block overflow-hidden rounded-lg border border-ink-200 bg-ink-50 hover:border-accent-400"
        aria-label={`Open ${label} in a new tab`}
      >
        {failed ? (
          <div className="flex h-24 items-center justify-center gap-2 px-2 text-center text-[11px] text-ink-500">
            <ImageIcon className="h-4 w-4" />
            Artifact unavailable (it may have expired).
          </div>
        ) : (
          <img
            src={src}
            alt={`${label} diagnostic artifact`}
            loading="lazy"
            className="h-24 w-full object-contain transition-transform group-hover:scale-[1.02]"
            onError={() => setFailed(true)}
          />
        )}
      </a>
      <figcaption className="mt-1.5 flex items-start justify-between gap-1 text-[11px] text-ink-600">
        <span>
          <span className="font-semibold text-ink-800">{label}.</span> {caption}
        </span>
        <ExternalLinkIcon className="mt-0.5 h-3 w-3 shrink-0 text-ink-400" />
      </figcaption>
    </figure>
  )
}

/**
 * Temporary diagnostic PNGs from the backend. These are not a diagnosis and
 * disappear with the history row.
 */
export function SegmentationPreviewPanel({ artifacts }: { artifacts: ArtifactLinks }) {
  const available = ARTIFACTS.map((artifact) => ({
    ...artifact,
    src: artifactUrl(artifacts[artifact.key]),
  })).filter((artifact) => artifact.src !== null)

  if (available.length === 0) return null

  return (
    <section
      className="rounded-lg border border-ink-200 bg-white p-4"
      aria-labelledby="segmentation-preview-heading"
      data-testid="segmentation-preview"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="segmentation-preview-heading" className="text-sm font-semibold text-ink-900">
          Temporary diagnostic artifacts
        </h3>
        <p className="text-[11px] text-ink-500">Click a thumbnail to open the full PNG.</p>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink-500">
        Leaf and lesion masks are intermediate pipeline outputs, not evidence of a specific
        disease. They are stored only for the current backend session and expire with the history
        row.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {available.map((artifact) => (
          <ArtifactThumbnail
            key={artifact.key}
            src={artifact.src}
            label={artifact.label}
            caption={artifact.caption}
          />
        ))}
      </div>
    </section>
  )
}
