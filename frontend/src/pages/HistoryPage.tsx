export function HistoryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">Prediction History</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-600">
          Temporary records from the currently running backend session.
        </p>
      </div>

      <div className="rounded-xl border border-warn-300 bg-warn-50 p-4 text-sm text-warn-700">
        History is temporary. Records and generated images are deleted after the configured expiry
        period, at backend restart, or when the server sleeps. Nothing is stored permanently.
      </div>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-ink-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-ink-700">Recent analyses</h2>
          <button
            type="button"
            disabled
            className="cursor-not-allowed rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-400"
            title="History is implemented in Phase 4-5"
          >
            Clear history
          </button>
        </div>

        <div className="flex flex-col items-center gap-2 px-5 py-14 text-center">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-ink-100"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-ink-400" fill="none" strokeWidth="1.6">
              <path d="M12 8v4l3 2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="12" cy="12" r="8" stroke="currentColor" />
            </svg>
          </span>
          <p className="text-sm font-medium text-ink-700">No predictions in this session</p>
          <p className="max-w-sm text-xs text-ink-500">
            Analysed images will be listed here with a thumbnail, timestamp, disease label,
            confidence, severity and status. The list is cleared when the backend restarts.
          </p>
        </div>
      </section>
    </div>
  )
}
