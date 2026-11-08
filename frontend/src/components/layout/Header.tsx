import { API_BASE_URL } from '../../services/api'
import { useHealth } from '../../hooks/useHealth'

type DisplayState = 'checking' | 'starting' | 'online' | 'offline'

const badgeStyles: Record<DisplayState, string> = {
  checking: 'border-warn-300 bg-warn-50 text-warn-700',
  starting: 'border-warn-300 bg-warn-50 text-warn-800',
  online: 'border-accent-200 bg-accent-50 text-accent-700',
  offline: 'border-red-200 bg-red-50 text-red-700',
}

const dotStyles: Record<DisplayState, string> = {
  checking: 'bg-warn-500 animate-pulse',
  starting: 'bg-warn-500 animate-pulse',
  online: 'bg-accent-500',
  offline: 'bg-red-500',
}

export function Header() {
  const { state, modelLoaded, modelVersion, lastChecked, refresh } = useHealth()

  const displayState: DisplayState =
    state === 'online' && !modelLoaded ? 'starting' : state

  const label =
    displayState === 'checking'
      ? 'Checking backend'
      : displayState === 'starting'
        ? 'Backend online · model starting'
        : displayState === 'online'
          ? 'Backend online'
          : 'Backend offline'

  const detail = [
    `${API_BASE_URL}/api/v1/health`,
    modelVersion ? `model ${modelVersion}` : 'no model version reported',
    lastChecked ? `checked ${lastChecked.toLocaleTimeString()}` : 'not checked yet',
  ].join(' · ')

  return (
    <header className="bg-ink-950 text-white">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-500/15 ring-1 ring-inset ring-accent-400/40"
          >
            <svg viewBox="0 0 24 24" className="h-6 w-6 text-accent-300" fill="none" strokeWidth="1.6">
              <path
                d="M12 21c0-6 3.5-10.5 8-12-1 6-4 9.5-8 12Z"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M12 21C12 15 8.5 10.5 4 9c1 6 4 9.5 8 12Z"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path d="M12 21v-7" stroke="currentColor" strokeLinecap="round" />
            </svg>
          </span>
          <div>
            <p className="text-lg font-semibold leading-tight tracking-tight">DhanyaDrishti</p>
            <p className="text-xs text-ink-300">Rice-leaf disease analysis · academic prototype</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="badge border-ink-700 bg-ink-900 text-ink-200">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" strokeWidth="1.8" aria-hidden="true">
              <path d="M4 18V9m6 9V5m6 13v-6" stroke="currentColor" strokeLinecap="round" />
            </svg>
            Model: Classical ML
          </span>
          <button
            type="button"
            onClick={refresh}
            className={`badge ${badgeStyles[displayState]} cursor-pointer hover:brightness-[0.98]`}
            title={`${detail}. Click to refresh.`}
            aria-label="Refresh backend and model status"
          >
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dotStyles[displayState]}`} />
            <span aria-live="polite">{label}</span>
            {displayState === 'online' && modelVersion ? (
              <span className="hidden text-[11px] font-normal opacity-80 sm:inline">
                · {modelVersion}
              </span>
            ) : null}
          </button>
        </div>
      </div>
    </header>
  )
}
