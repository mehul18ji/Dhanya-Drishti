import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Callout } from '../components/common/Callout'
import { ConfirmDialog } from '../components/common/ConfirmDialog'
import { ErrorNotice } from '../components/common/ErrorNotice'
import { ClockIcon, RefreshIcon, TrashIcon } from '../components/common/Icons'
import { PageHeader } from '../components/common/PageHeader'
import { Spinner } from '../components/common/Spinner'
import { HistoryTable } from '../components/history/HistoryTable'
import { useHistory } from '../hooks/useHistory'
import { TEMPORARY_STORAGE_NOTICE, SEVERITY_DISCLAIMER } from '../utils/disclaimers'
import { formatTime } from '../utils/format'

function EmptyHistory() {
  return (
    <div
      className="flex flex-col items-center justify-center px-6 py-14 text-center"
      data-testid="history-empty"
    >
      <ClockIcon className="h-9 w-9 text-ink-400" />
      <h2 className="mt-3 text-base font-semibold text-ink-900">No predictions yet</h2>
      <p className="mt-1 max-w-md text-sm leading-relaxed text-ink-600">
        Analysed images with a disease label appear here for the current backend session. Rejected
        uploads, invalid files and service errors are never stored.
      </p>
      <Link
        to="/"
        className="mt-4 rounded-lg bg-ink-900 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-800"
      >
        Analyze a leaf
      </Link>
    </div>
  )
}

export function HistoryPage() {
  const history = useHistory()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const handleClear = async () => {
    const deleted = await history.clear()
    if (deleted !== null) {
      setNotice(
        deleted === 0
          ? 'History was already empty.'
          : `Removed ${deleted} temporary record${deleted === 1 ? '' : 's'} and the associated artifact files.`,
      )
    }
    setConfirmOpen(false)
  }

  const hasItems = history.items.length > 0

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Session history"
        title="Prediction History"
        description="Temporary records from the currently running backend session. Each record and its images are deleted automatically 60 minutes after creation, and nothing here survives a restart or server sleep."
        actions={
          <>
            <button
              type="button"
              onClick={history.reload}
              disabled={history.refreshing || history.state === 'loading'}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-ink-300 bg-white px-3 py-2 text-xs font-semibold text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
            >
              {history.refreshing ? (
                <Spinner className="h-3.5 w-3.5" />
              ) : (
                <RefreshIcon className="h-3.5 w-3.5" />
              )}
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              disabled={!hasItems || history.clearing}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {history.clearing ? (
                <Spinner className="h-3.5 w-3.5 text-red-700" />
              ) : (
                <TrashIcon className="h-3.5 w-3.5" />
              )}
              Clear history
            </button>
          </>
        }
      />

      <Callout tone="warning" title="Temporary storage only" className="block">
        <p>{TEMPORARY_STORAGE_NOTICE}</p>
        <p className="mt-1">
          Only results with a disease label are stored. Rejected uploads and upload-level errors
          (413 / 415 / 422 / 503) never appear here.
        </p>
      </Callout>

      {notice ? (
        <Callout tone="success" title="History updated" role="status">
          <div className="flex flex-wrap items-center gap-3">
            <span>{notice}</span>
            <button
              type="button"
              onClick={() => setNotice(null)}
              className="text-xs font-semibold text-accent-800 underline"
            >
              Dismiss
            </button>
          </div>
        </Callout>
      ) : null}

      {history.clearError ? (
        <div data-testid="clear-history-error">
          <ErrorNotice
            error={history.clearError}
            onRetry={() => setConfirmOpen(true)}
            retryLabel="Try again"
            retrying={history.clearing}
          />
        </div>
      ) : null}

      <section className="card overflow-hidden" aria-labelledby="history-table-heading">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-200 px-5 py-3">
          <h2 id="history-table-heading" className="text-sm font-semibold text-ink-700">
            Recent analyses
            {history.state === 'success' ? (
              <span className="ml-2 font-normal text-ink-500" data-testid="history-count">
                {history.count} record{history.count === 1 ? '' : 's'}
              </span>
            ) : null}
          </h2>
          <p className="text-[11px] text-ink-500">
            {history.lastLoadedAt
              ? `Updated ${formatTime(history.lastLoadedAt.toISOString())}`
              : 'Not loaded yet'}
            {history.refreshing ? ' · refreshing…' : ''}
          </p>
        </div>

        {history.state === 'loading' ? (
          <div
            className="flex items-center justify-center gap-3 px-6 py-14 text-sm text-ink-600"
            data-testid="history-loading"
          >
            <Spinner className="h-4 w-4 text-accent-600" />
            Loading temporary history…
          </div>
        ) : null}

        {history.state === 'error' && history.error ? (
          <div className="p-5" data-testid="history-error">
            <ErrorNotice
              error={history.error}
              onRetry={history.reload}
              autoRetrying={history.autoRetrying}
            />
          </div>
        ) : null}

        {history.state === 'success' && !hasItems ? <EmptyHistory /> : null}

        {history.state === 'success' && hasItems ? (
          <div data-testid="history-list">
            <HistoryTable items={history.items} />
          </div>
        ) : null}
      </section>

      <Callout tone="warning" title="Required severity disclaimer" className="block">
        <p>{SEVERITY_DISCLAIMER}</p>
        <p className="mt-1">
          A severity badge is shown only when the backend produced a reliable lesion-area
          measurement. Unreliable or missing measurements remain “Not reported”.
        </p>
      </Callout>

      <p className="text-xs leading-relaxed text-ink-500">
        Model scores in this table are decision-function margins, not probabilities or confidence
        percentages. Severity is an experimental lesion-area estimate and is never inferred when the
        measurement is unreliable.
      </p>

      <ConfirmDialog
        open={confirmOpen}
        title="Clear temporary history?"
        description={`This removes all ${history.count} temporary prediction record${
          history.count === 1 ? '' : 's'
        } and their uploaded images and diagnostic masks from this backend session. It cannot be undone.`}
        confirmLabel="Clear history"
        busy={history.clearing}
        onConfirm={() => void handleClear()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
