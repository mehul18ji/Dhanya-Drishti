import { useEffect, useRef } from 'react'

import { Spinner } from './Spinner'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  busy = false,
  tone = 'danger',
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  cancelLabel?: string
  busy?: boolean
  tone?: 'danger' | 'neutral'
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    confirmRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, busy, onCancel])

  if (!open) return null

  const confirmClass =
    tone === 'danger'
      ? 'bg-red-600 text-white hover:bg-red-700'
      : 'bg-ink-900 text-white hover:bg-ink-800'

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink-950/60 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-md rounded-t-2xl border border-ink-200 bg-white p-5 shadow-float sm:rounded-2xl"
      >
        <h2 id="confirm-dialog-title" className="text-lg font-semibold text-ink-900">
          {title}
        </h2>
        <p
          id="confirm-dialog-description"
          className="mt-2 text-sm leading-relaxed text-ink-600"
        >
          {description}
        </p>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="w-full rounded-lg border border-ink-300 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-60 sm:w-auto"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto ${confirmClass}`}
          >
            {busy ? <Spinner className="h-4 w-4 text-white" /> : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
