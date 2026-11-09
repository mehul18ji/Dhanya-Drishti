import {
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
} from 'react'

import { DEFAULT_UPLOAD_LIMIT_MB } from '../../services/api'
import { ACCEPT_ATTRIBUTE, validateUploadFile } from '../../utils/upload'
import { AlertTriangleIcon, UploadIcon } from '../common/Icons'

export function ImageUploader({
  file,
  onFileSelected,
  disabled = false,
  maxSizeMb = DEFAULT_UPLOAD_LIMIT_MB,
}: {
  file: File | null
  onFileSelected: (file: File) => void
  disabled?: boolean
  maxSizeMb?: number
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [clientError, setClientError] = useState<string | null>(null)

  const openPicker = () => {
    if (!disabled) inputRef.current?.click()
  }

  const acceptFile = (candidate: File | undefined) => {
    if (!candidate || disabled) return
    const check = validateUploadFile(candidate, maxSizeMb)
    if (!check.ok) {
      setClientError(check.error)
      return
    }
    setClientError(null)
    onFileSelected(candidate)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    acceptFile(event.dataTransfer.files?.[0])
  }

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    // input.click() bubbles back here; ignore it or the picker would recurse.
    if (event.target === inputRef.current) return
    openPicker()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    openPicker()
  }

  const label = file ? 'Replace the selected image' : 'Upload a rice-leaf image'

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label={label}
        aria-disabled={disabled || undefined}
        aria-describedby="uploader-instruction uploader-hint"
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          'group flex min-h-[220px] cursor-pointer select-none flex-col items-center justify-center rounded-2xl border-2 border-dashed px-5 py-8 text-center transition-all duration-200 sm:min-h-[240px] sm:px-6',
          dragging
            ? 'border-accent-500 bg-accent-50 shadow-inner'
            : 'border-ink-300 bg-white/60 hover:border-accent-500 hover:bg-accent-50/40 dark:border-white/20 dark:bg-white/5 dark:hover:bg-accent-900/20',
          disabled ? 'cursor-not-allowed opacity-60' : 'active:scale-[0.995]',
          'focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2',
        ].join(' ')}
        data-testid="upload-dropzone"
      >
        <span
          aria-hidden="true"
          className={[
            'flex h-14 w-14 items-center justify-center rounded-full transition-colors',
            dragging
              ? 'bg-accent-500 text-white'
              : 'bg-accent-500/10 text-accent-700 group-hover:bg-accent-500 group-hover:text-white',
          ].join(' ')}
        >
          <UploadIcon className="h-6 w-6" />
        </span>
        <p
          id="uploader-instruction"
          className="mt-4 text-base font-semibold text-ink-900 sm:text-lg"
        >
          {label}
        </p>
        <p className="mt-1 max-w-xs text-xs leading-relaxed text-ink-600 sm:text-sm">
          Tap anywhere in this box to choose a photo, or drag and drop one here.
        </p>
        <p id="uploader-hint" className="mt-3 text-[11px] font-medium text-ink-500">
          JPG · JPEG · PNG · WEBP · up to {maxSizeMb} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          disabled={disabled}
          onChange={(event) => {
            acceptFile(event.target.files?.[0])
            // Allow choosing the same file again after a client-side rejection.
            event.target.value = ''
          }}
        />
      </div>

      {clientError ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
          {clientError}
        </p>
      ) : null}
    </div>
  )
}
