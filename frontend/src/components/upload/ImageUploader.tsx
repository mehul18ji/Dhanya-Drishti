import { useRef, useState, type DragEvent } from 'react'

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

  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-labelledby="uploader-instruction"
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          'rounded-xl border-2 border-dashed px-5 py-7 text-center transition-colors',
          dragging
            ? 'border-accent-500 bg-accent-50'
            : 'border-ink-300 bg-ink-50/60 hover:border-accent-400',
          disabled ? 'opacity-60' : '',
        ].join(' ')}
      >
        <UploadIcon className="mx-auto h-9 w-9 text-accent-600" />
        <p id="uploader-instruction" className="mt-3 text-sm font-semibold text-ink-900">
          {file ? 'Replace the selected image' : 'Drag and drop a rice-leaf image here'}
        </p>
        <p className="mt-1 text-xs text-ink-500">
          JPG, JPEG, PNG or WEBP · up to {maxSizeMb} MB
        </p>
        <button
          type="button"
          onClick={openPicker}
          disabled={disabled}
          className="mt-3 inline-flex items-center rounded-lg border border-ink-300 bg-white px-4 py-2 text-sm font-semibold text-ink-800 shadow-sm hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Browse files
        </button>
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
