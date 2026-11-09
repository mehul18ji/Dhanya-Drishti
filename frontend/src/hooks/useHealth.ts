import { useCallback, useEffect, useState } from 'react'

import { getHealth } from '../services/api'
import { describeApiError, isAbortError } from '../utils/errors'
import type { FriendlyError } from '../utils/errors'

export type BackendState = 'checking' | 'online' | 'offline'

/**
 * Keep-alive cadence: free hosts (Render) sleep after ~15 idle minutes, so one
 * health request per minute keeps the service responsive without wasting quota.
 */
export const KEEP_ALIVE_INTERVAL_MS = 60_000

export interface HealthState {
  state: BackendState
  modelLoaded: boolean
  modelVersion: string | null
  lastChecked: Date | null
  error: FriendlyError | null
  refresh: () => void
}

/**
 * Live `/api/v1/health` state with cold-start retries.
 *
 * A healthy backend without a loaded model is reported as `online` with
 * `modelLoaded: false`; the UI then says the model is starting rather than
 * pretending a prediction is possible.
 *
 * The regular poll doubles as the **keep-alive ping**: a free-tier backend spins
 * down after ~15 minutes without traffic, so an open dashboard keeps hitting
 * `/api/v1/health` once a minute, which is frequent enough to stay awake and
 * cheap enough to leave running. Polling continues while the tab is hidden
 * (browsers throttle it to about once a minute, still well inside the window)
 * and a visibility/online event forces an immediate check on return.
 */
export function useHealth({
  pollIntervalMs = KEEP_ALIVE_INTERVAL_MS,
  retryIntervalMs = 5_000,
}: {
  pollIntervalMs?: number
  retryIntervalMs?: number
} = {}): HealthState {
  const [state, setState] = useState<BackendState>('checking')
  const [modelLoaded, setModelLoaded] = useState(false)
  const [modelVersion, setModelVersion] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [error, setError] = useState<FriendlyError | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)

  const refresh = useCallback(() => setRefreshToken((token) => token + 1), [])

  useEffect(() => {
    let active = true
    let timer: number | undefined
    let controller: AbortController | null = null

    const schedule = (delay: number) => {
      if (!active) return
      timer = window.setTimeout(() => void check(), delay)
    }

    const check = async () => {
      controller?.abort()
      controller = new AbortController()
      try {
        const health = await getHealth(controller.signal)
        if (!active) return
        setState('online')
        setModelLoaded(health.model_loaded)
        setModelVersion(health.model_version)
        setError(null)
        setLastChecked(new Date())
        schedule(health.model_loaded ? pollIntervalMs : retryIntervalMs)
      } catch (caught) {
        if (!active || isAbortError(caught)) return
        setState('offline')
        setModelLoaded(false)
        setModelVersion(null)
        setError(describeApiError(caught, 'health'))
        setLastChecked(new Date())
        schedule(retryIntervalMs)
      }
    }

    void check()

    return () => {
      active = false
      controller?.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [pollIntervalMs, retryIntervalMs, refreshToken])

  // Re-check immediately when connectivity returns or the tab becomes active
  // again; a backgrounded tab may have missed the backend waking up.
  useEffect(() => {
    const nudge = () => setRefreshToken((token) => token + 1)
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') nudge()
    }
    window.addEventListener('online', nudge)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.removeEventListener('online', nudge)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  return { state, modelLoaded, modelVersion, lastChecked, error, refresh }
}
