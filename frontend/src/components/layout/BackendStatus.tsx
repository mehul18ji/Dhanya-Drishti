import type { HealthState } from '../../hooks/useHealth'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { API_BASE_URL, API_CONFIG_ERROR } from '../../services/api'
import { apiTargetLabel, resolveApiTarget, type ApiTarget } from '../../utils/apiTarget'

type ConnectionState = 'online' | 'starting' | 'checking' | 'offline' | 'config'

interface ConnectionOptions {
  apiBaseUrl?: string
  configError?: string | null
  browserOnline?: boolean
}

export interface BackendConnectionView {
  state: ConnectionState
  label: string
  target: ApiTarget
  targetLabel: string
  detail: string
  pillClass: string
  dotClass: string
}

const PILL_CLASSES: Record<ConnectionState, string> = {
  online: 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100',
  starting: 'border-amber-300/35 bg-amber-300/10 text-amber-100',
  checking: 'border-amber-300/35 bg-amber-300/10 text-amber-100',
  offline: 'border-red-400/35 bg-red-400/10 text-red-100',
  config: 'border-red-400/35 bg-red-400/10 text-red-100',
}

const DOT_CLASSES: Record<ConnectionState, string> = {
  online: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]',
  starting: 'animate-pulse bg-amber-300',
  checking: 'animate-pulse bg-amber-300',
  offline: 'bg-red-400',
  config: 'bg-red-400',
}

/** Human-readable connection state, independent of React for easy testing. */
export function describeBackendConnection(
  health: Pick<HealthState, 'state' | 'modelLoaded'>,
  {
    apiBaseUrl = API_BASE_URL,
    configError = API_CONFIG_ERROR,
    browserOnline = true,
  }: ConnectionOptions = {},
): BackendConnectionView {
  const target = resolveApiTarget(apiBaseUrl)
  const targetLabel = apiTargetLabel(target)
  const base = { target, targetLabel }

  if (configError) {
    return {
      ...base,
      state: 'config',
      label: 'API not configured',
      detail: configError,
      pillClass: PILL_CLASSES.config,
      dotClass: DOT_CLASSES.config,
    }
  }

  if (!browserOnline) {
    return {
      ...base,
      state: 'offline',
      label: "You're offline",
      detail:
        'This browser has no network connection. The dashboard will reconnect automatically when you are back online.',
      pillClass: PILL_CLASSES.offline,
      dotClass: DOT_CLASSES.offline,
    }
  }

  if (health.state === 'checking') {
    return {
      ...base,
      state: 'checking',
      label: 'Checking API',
      detail: `Contacting the ${targetLabel} analysis service at ${apiBaseUrl}.`,
      pillClass: PILL_CLASSES.checking,
      dotClass: DOT_CLASSES.checking,
    }
  }

  if (health.state === 'offline') {
    const detail =
      target === 'local'
        ? `No response from the local analysis service at ${apiBaseUrl}. Start the FastAPI backend to analyze images.`
        : target === 'render'
          ? `No response from the Render analysis service at ${apiBaseUrl}. A free instance may be asleep and can take up to a minute to wake; this page retries automatically.`
          : `No response from the hosted analysis service at ${apiBaseUrl}. The service may be starting; this page retries automatically.`

    return {
      ...base,
      state: 'offline',
      label: target === 'local' ? 'Backend offline' : target === 'render' ? 'Render API offline' : 'API offline',
      detail,
      pillClass: PILL_CLASSES.offline,
      dotClass: DOT_CLASSES.offline,
    }
  }

  if (!health.modelLoaded) {
    return {
      ...base,
      state: 'starting',
      label: 'API starting',
      detail: `The ${targetLabel} API is reachable, but the model bundle is still loading. Analysis stays disabled until it is ready.`,
      pillClass: PILL_CLASSES.starting,
      dotClass: DOT_CLASSES.starting,
    }
  }

  return {
    ...base,
    state: 'online',
    label: 'Connected',
    detail: `Connected to the ${targetLabel} analysis service at ${apiBaseUrl}.`,
    pillClass: PILL_CLASSES.online,
    dotClass: DOT_CLASSES.online,
  }
}

/**
 * Compact, read-only connection indicator. It is deliberately not a button:
 * health checks refresh themselves, so there is nothing the visitor must click.
 */
export function BackendStatus({
  health,
  apiBaseUrl = API_BASE_URL,
  configError = API_CONFIG_ERROR,
}: {
  health: Pick<HealthState, 'state' | 'modelLoaded'>
  apiBaseUrl?: string
  configError?: string | null
}) {
  const browserOnline = useOnlineStatus()
  const view = describeBackendConnection(health, { apiBaseUrl, configError, browserOnline })

  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={`${view.label} · ${view.targetLabel} API. ${view.detail}`}
      title={view.detail}
      data-testid="backend-status"
      data-state={view.state}
      data-target={view.target}
      className={`inline-flex cursor-default select-none items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold leading-none ${view.pillClass}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${view.dotClass}`} />
      <span>{view.label}</span>
      <span aria-hidden="true" className="hidden text-white/50 sm:inline">
        · {view.targetLabel}
      </span>
    </span>
  )
}
