import { useState } from 'react'

import { artifactUrl } from '../../services/api'
import type { ArtifactLinks } from '../../types/api'
import { ArtifactPreview, type PreviewableArtifact } from '../common/ArtifactPreview'
import { ImageIcon, MaximizeIcon } from '../common/Icons'

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

type ResolvedArtifact = Artifact & { src: string }

function ArtifactThumbnail({
  artifact,
  onPreview,
}: {
  artifact: ResolvedArtifact
  onPreview: () => void
}) {
  const [failed, setFailed] = useState(false)

  return (
    <figure className="min-w-0">
      <button
        type="button"
        onClick={onPreview}
        aria-label={`Preview ${artifact.label} artifact full screen`}
        className="group relative block w-full overflow-hidden rounded-xl border border-ink-200 bg-ink-100 transition hover:border-accent-400 focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2"
      >
        {failed ? (
          <div className="flex h-28 items-center justify-center gap-2 px-2 text-center text-[11px] text-ink-500 sm:h-24">
            <ImageIcon className="h-4 w-4" />
            Artifact unavailable (it may have expired).
          </div>
        ) : (
          <img
            src={artifact.src}
            alt={`${artifact.label} diagnostic artifact`}
            loading="lazy"
            decoding="async"
            className="h-28 w-full object-contain transition-transform duration-300 group-hover:scale-[1.03] sm:h-24"
            onError={() => setFailed(true)}
          />
        )}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex items-end justify-end bg-gradient-to-t from-ink-950/25 to-transparent p-2 opacity-70 transition group-hover:opacity-100"
        >
          <span className="rounded-full bg-ink-950/70 p-1.5 text-white backdrop-blur">
            <MaximizeIcon className="h-3.5 w-3.5" />
          </span>
        </span>
      </button>
      <figcaption className="mt-1.5 text-[11px] leading-relaxed text-ink-600">
        <span className="font-semibold text-ink-800">{artifact.label}.</span> {artifact.caption}
      </figcaption>
    </figure>
  )
}

/**
 * Temporary diagnostic PNGs from the backend. Thumbnails open an in-app
 * full-screen preview; downloading happens only from the viewer's button.
 */
export function SegmentationPreviewPanel({ artifacts }: { artifacts: ArtifactLinks }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const available = ARTIFACTS.map((artifact) => {
    const src = artifactUrl(artifacts[artifact.key])
    return src ? { ...artifact, src } : null
  }).filter((artifact): artifact is ResolvedArtifact => artifact !== null)

  if (available.length === 0) return null

  const items: PreviewableArtifact[] = available.map((artifact) => ({
    src: artifact.src,
    label: artifact.label,
    caption: artifact.caption,
  }))

  return (
    <section
      className="rounded-xl border border-ink-200 bg-white p-4"
      aria-labelledby="segmentation-preview-heading"
      data-testid="segmentation-preview"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="segmentation-preview-heading" className="text-sm font-semibold text-ink-900">
          Temporary diagnostic artifacts
        </h3>
        <p className="text-[11px] text-ink-500">Tap for full-screen preview</p>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink-500">
        Leaf and lesion masks are intermediate pipeline outputs, not evidence of a specific
        disease. They are stored only for the current backend session and expire with the history
        row. The preview never downloads the file; use Download inside the viewer.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {available.map((artifact, index) => (
          <ArtifactThumbnail
            key={artifact.key}
            artifact={artifact}
            onPreview={() => setActiveIndex(index)}
          />
        ))}
      </div>

      <ArtifactPreview
        items={items}
        index={activeIndex}
        onIndexChange={setActiveIndex}
        onClose={() => setActiveIndex(null)}
      />
    </section>
  )
}
