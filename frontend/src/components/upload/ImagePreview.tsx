import { useEffect, useState } from 'react'

import { useObjectUrl } from '../../hooks/useObjectUrl'
import { formatFileSize } from '../../utils/format'
import { ArtifactPreview } from '../common/ArtifactPreview'
import { ImageIcon, MaximizeIcon, XIcon } from '../common/Icons'

interface Dimensions {
  width: number
  height: number
}

function orientationLabel({ width, height }: Dimensions): string {
  if (width === height) return 'Square'
  return width > height ? 'Landscape' : 'Portrait'
}

const SINGLE_ITEM_INDEX = () => {}

export function ImagePreview({
  file,
  onRemove,
  disabled = false,
}: {
  file: File
  onRemove: () => void
  disabled?: boolean
}) {
  const src = useObjectUrl(file)
  const [dimensions, setDimensions] = useState<Dimensions | null>(null)
  const [failed, setFailed] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    setDimensions(null)
    setFailed(false)
  }, [src])

  return (
    <div className="space-y-3" data-testid="image-preview">
      <div className="relative overflow-hidden rounded-xl border border-ink-200 bg-ink-100">
        {src && !failed ? (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            aria-label={`Open full-screen preview of ${file.name}`}
            className="group relative block w-full cursor-zoom-in bg-ink-100/60"
          >
            <img
              src={src}
              alt={`Preview of the selected leaf image: ${file.name}`}
              className="mx-auto max-h-[52vh] w-full object-contain sm:max-h-[420px]"
              data-testid="preview-image"
              onLoad={(event) =>
                setDimensions({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
              onError={() => setFailed(true)}
            />
            <span
              aria-hidden="true"
              className="pointer-events-none absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-full bg-ink-950/70 px-2.5 py-1 text-[10px] font-semibold text-white backdrop-blur transition group-hover:bg-accent-600"
            >
              <MaximizeIcon className="h-3 w-3" />
              Full screen
            </span>
          </button>
        ) : (
          <div className="flex min-h-[180px] flex-col items-center justify-center gap-2 px-4 py-8 text-center text-sm text-ink-600">
            <ImageIcon className="h-7 w-7 text-ink-400" />
            {failed ? (
              <p>
                The preview could not be rendered. The file may be corrupt; the backend will
                reject it if it cannot be decoded.
              </p>
            ) : (
              <p>Preparing preview…</p>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          className="absolute right-2 top-2 inline-flex h-9 items-center gap-1 rounded-full border border-ink-300 bg-white/95 px-2.5 text-xs font-semibold text-ink-700 shadow-sm hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
          aria-label="Remove selected image"
        >
          <XIcon className="h-3.5 w-3.5" />
          Remove
        </button>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div className="col-span-2 min-w-0">
          <dt className="font-medium text-ink-500">File</dt>
          <dd className="truncate text-ink-800" title={file.name}>
            {file.name}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink-500">Size</dt>
          <dd className="text-ink-800">{formatFileSize(file.size)}</dd>
        </div>
        <div>
          <dt className="font-medium text-ink-500">Type</dt>
          <dd className="uppercase text-ink-800">{file.type || 'Unknown'}</dd>
        </div>
        <div>
          <dt className="font-medium text-ink-500">Dimensions</dt>
          <dd className="text-ink-800" data-testid="preview-dimensions">
            {dimensions ? `${dimensions.width} × ${dimensions.height} px` : 'Reading…'}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink-500">Orientation</dt>
          <dd className="text-ink-800" data-testid="preview-orientation">
            {dimensions ? orientationLabel(dimensions) : '—'}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-ink-500">
        Tap the image to preview it full screen. Previews are scaled to fit without stretching, so
        portrait and landscape photos keep their original proportions.
      </p>

      <ArtifactPreview
        items={src ? [{ src, label: 'Selected image', caption: file.name, filename: file.name }] : []}
        index={expanded && src ? 0 : null}
        onIndexChange={SINGLE_ITEM_INDEX}
        onClose={() => setExpanded(false)}
      />
    </div>
  )
}
