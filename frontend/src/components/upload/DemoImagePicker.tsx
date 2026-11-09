import { useState } from 'react'

import { DEFAULT_UPLOAD_LIMIT_MB } from '../../services/api'
import { validateUploadFile } from '../../utils/upload'
import { AlertTriangleIcon } from '../common/Icons'
import { Spinner } from '../common/Spinner'

export interface DemoImage {
  /** Stable id used for test ids and loading state. */
  readonly id: string
  /** Supported disease the sample illustrates. */
  readonly label: string
  /** File name under `public/demo/`, also used as the uploaded file name. */
  readonly filename: string
  readonly alt: string
}

/**
 * Three development-split samples bundled with the dashboard so a visitor can
 * try the whole flow without the dataset or repository. They are UI samples,
 * not evidence of accuracy — the only reported generalization figure is the
 * frozen 24-image held-out evaluation.
 *
 * The names are deliberately neutral. The chosen file name appears in the
 * preview, the result card and the history table, so it must not hint at the
 * expected label — otherwise a correct prediction looks like a hard-coded
 * answer instead of a model result.
 */
export const DEMO_IMAGES: readonly DemoImage[] = [
  {
    id: 'demo-1',
    label: 'Demo Image 1',
    filename: 'demo-image-1.jpg',
    alt: 'Demo rice leaf photograph 1',
  },
  {
    id: 'demo-2',
    label: 'Demo Image 2',
    filename: 'demo-image-2.jpg',
    alt: 'Demo rice leaf photograph 2',
  },
  {
    id: 'demo-3',
    label: 'Demo Image 3',
    filename: 'demo-image-3.jpg',
    alt: 'Demo rice leaf photograph 3',
  },
]

const BASE_URL = import.meta.env.BASE_URL.endsWith('/')
  ? import.meta.env.BASE_URL
  : `${import.meta.env.BASE_URL}/`

/** Absolute-in-app URL of a bundled demo image (works under any Vite base). */
export function demoImageUrl(image: DemoImage): string {
  return `${BASE_URL}demo/${image.filename}`
}

/**
 * Pick one of the bundled demo leaves and hand it to the normal upload flow.
 *
 * The image is fetched as a `Blob` and wrapped in a real `File`, so the
 * existing preview, client-side validation, multipart upload and result
 * rendering all behave exactly as for a file the visitor chose themselves.
 */
export function DemoImagePicker({
  onFileSelected,
  disabled = false,
  selectedName = null,
  maxSizeMb = DEFAULT_UPLOAD_LIMIT_MB,
}: {
  onFileSelected: (file: File) => void
  disabled?: boolean
  selectedName?: string | null
  maxSizeMb?: number
}) {
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const choose = async (image: DemoImage) => {
    if (disabled || loadingId) return
    setLoadingId(image.id)
    setError(null)
    try {
      const response = await fetch(demoImageUrl(image), { cache: 'no-store' })
      if (!response.ok) throw new Error(`Demo image request failed: ${response.status}`)
      const blob = await response.blob()
      const file = new File([blob], image.filename, {
        type: blob.type || 'image/jpeg',
      })
      const check = validateUploadFile(file, maxSizeMb)
      if (!check.ok) {
        setError(check.error)
        return
      }
      onFileSelected(file)
    } catch {
      setError(
        'The demo image could not be loaded. Check the connection and try again, or choose a file from your device.',
      )
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
          Or try a demo leaf
        </p>
        <span className="hidden shrink-0 text-[11px] text-ink-400 sm:inline">
          No upload needed
        </span>
      </div>

      <div
        className="mt-2 grid grid-cols-3 gap-1.5 sm:gap-3"
        data-testid="demo-image-picker"
      >
        {DEMO_IMAGES.map((image) => {
          const selected = selectedName === image.filename
          const loading = loadingId === image.id
          return (
            <button
              key={image.id}
              type="button"
              onClick={() => void choose(image)}
              disabled={disabled || loadingId !== null}
              aria-pressed={selected}
              aria-label={`Use ${image.label}`}
              data-testid={`demo-tile-${image.id}`}
              className={[
                'group min-w-0 rounded-xl border p-1 text-left transition focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:p-1.5',
                selected
                  ? 'border-accent-500 bg-accent-50/60 ring-1 ring-accent-500'
                  : 'border-ink-200 bg-white/70 hover:border-accent-400 hover:bg-accent-50/40 dark:border-white/15 dark:bg-white/5',
              ].join(' ')}
            >
              <span className="relative block overflow-hidden rounded-lg bg-ink-100">
                <img
                  src={demoImageUrl(image)}
                  alt={image.alt}
                  loading="lazy"
                  decoding="async"
                  className="aspect-[4/3] w-full object-cover transition duration-200 group-hover:scale-[1.03]"
                />
                {loading ? (
                  <span className="absolute inset-0 flex items-center justify-center bg-ink-950/50">
                    <Spinner className="h-4 w-4 text-white" />
                  </span>
                ) : null}
                {selected && !loading ? (
                  <span className="absolute right-1 top-1 rounded-full bg-accent-600 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                    Selected
                  </span>
                ) : null}
              </span>
              <span className="mt-1 block text-center text-[10px] font-semibold leading-tight text-ink-700 sm:text-xs">
                {image.label}
              </span>
            </button>
          )
        })}
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">
        Demo samples are development images bundled with the dashboard. They are for trying the
        interface; they are not a benchmark and do not measure real-world accuracy.
      </p>

      {error ? (
        <p
          role="alert"
          className="mt-2 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
          {error}
        </p>
      ) : null}
    </div>
  )
}
