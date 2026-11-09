import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { artifactFilename, downloadArtifact } from '../../utils/download'
import { DownloadIcon, ImageIcon, XIcon } from './Icons'

export interface PreviewableArtifact {
  src: string
  label: string
  caption?: string
  filename?: string
}

/**
 * Full-screen artifact viewer. Clicking a thumbnail opens this dialog; the PNG
 * is only saved when the user presses Download inside it.
 */
export function ArtifactPreview({
  items,
  index,
  onIndexChange,
  onClose,
}: {
  items: PreviewableArtifact[]
  index: number | null
  onIndexChange: (index: number) => void
  onClose: () => void
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [imageFailed, setImageFailed] = useState(false)

  const open = index !== null && items.length > 0
  const active = open && index !== null ? items[index] : null

  useEffect(() => {
    if (!open) return
    restoreFocusRef.current = document.activeElement as HTMLElement | null
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (items.length < 2 || index === null) return
      if (event.key === 'ArrowRight') {
        onIndexChange((index + 1) % items.length)
      }
      if (event.key === 'ArrowLeft') {
        onIndexChange((index - 1 + items.length) % items.length)
      }
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      restoreFocusRef.current?.focus?.()
    }
  }, [open, index, items.length, onClose, onIndexChange])

  useEffect(() => {
    setDownloadError(null)
    setImageFailed(false)
  }, [index, active?.src])

  if (!open || !active || index === null) return null

  const download = async () => {
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadArtifact(active.src, active.filename ?? artifactFilename(active.label))
    } catch {
      setDownloadError(
        'The artifact could not be downloaded. It may have expired, or the backend may be waking up. Try again in a moment.',
      )
    } finally {
      setDownloading(false)
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col bg-ink-950/90 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${active.label} preview`}
        className="flex min-h-0 flex-1 flex-col p-3 sm:p-6"
      >
        <div className="flex items-start justify-between gap-3 text-white">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/55">
              Temporary artifact
            </p>
            <h2 className="mt-0.5 truncate text-base font-semibold sm:text-lg">{active.label}</h2>
            {active.caption ? (
              <p className="mt-0.5 hidden text-xs leading-relaxed text-white/60 sm:block">
                {active.caption}
              </p>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => void download()}
              disabled={downloading}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-semibold text-ink-900 shadow-sm transition hover:bg-accent-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <DownloadIcon className="h-4 w-4" />
              {downloading ? 'Preparing…' : 'Download'}
            </button>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close preview"
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/25 bg-white/10 text-white transition hover:bg-white/20"
            >
              <XIcon className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div
          className="mt-3 flex min-h-0 flex-1 items-center justify-center"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose()
          }}
        >
          {imageFailed ? (
            <div
              role="status"
              data-testid="artifact-image-fallback"
              className="max-w-md rounded-xl border border-white/20 bg-white/10 px-5 py-6 text-center text-sm leading-relaxed text-white/80"
            >
              This temporary artifact could not be loaded. It may have expired, or the backend may
              be waking from sleep. Close this viewer and retry in a moment.
            </div>
          ) : (
            <img
              src={active.src}
              alt={`${active.label} full-size preview`}
              className="max-h-full max-w-full rounded-xl object-contain shadow-2xl"
              data-testid="artifact-full-image"
              onError={() => setImageFailed(true)}
            />
          )}
        </div>

        <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-white/55">
          <p className="min-w-0 truncate">
            {active.caption ?? 'Stored only for the current backend session.'}
          </p>
          {items.length > 1 ? (
            <p className="hidden shrink-0 sm:block">← → to browse · Esc to close</p>
          ) : (
            <p className="hidden shrink-0 sm:block">Esc to close</p>
          )}
        </div>

        {downloadError ? (
          <p
            role="alert"
            className="mt-2 flex items-center gap-2 rounded-lg bg-red-500/20 px-3 py-2 text-xs text-red-100"
          >
            <ImageIcon className="h-4 w-4 shrink-0" />
            {downloadError}
          </p>
        ) : null}
      </div>
    </div>,
    document.body,
  )
}
