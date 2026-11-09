import { useCallback, useEffect, useRef, useState } from 'react'

import { deleteHistory, getHistory } from '../services/api'
import type { HistoryItem } from '../types/api'
import { describeApiError, isAbortError } from '../utils/errors'
import type { FriendlyError } from '../utils/errors'

export type HistoryLoadState = 'loading' | 'success' | 'error'

export interface HistoryState {
  items: HistoryItem[]
  count: number
  state: HistoryLoadState
  error: FriendlyError | null
  refreshing: boolean
  lastLoadedAt: Date | null
  autoRetrying: boolean
  reload: () => void
  clear: () => Promise<number | null>
  clearing: boolean
  clearError: FriendlyError | null
}

const RETRY_BASE_MS = 4_000
const RETRY_MAX_MS = 30_000
const MAX_AUTO_RETRIES = 6

/**
 * Temporary history client.
 *
 * Only labelled results are stored by the backend, so any defensive `rejected`
 * row is filtered out rather than displayed as a diagnosis. Because a free
 * Render instance may be asleep, retryable failures are retried automatically
 * with backoff; the Retry button remains available for an immediate attempt.
 */
export function useHistory(limit = 50): HistoryState {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [count, setCount] = useState(0)
  const [state, setState] = useState<HistoryLoadState>('loading')
  const [error, setError] = useState<FriendlyError | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null)
  const [autoRetrying, setAutoRetrying] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [clearing, setClearing] = useState(false)
  const [clearError, setClearError] = useState<FriendlyError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<number | null>(null)

  const reload = useCallback(() => {
    retryCountRef.current = 0
    setReloadToken((token) => token + 1)
  }, [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    controllerRef.current = controller

    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
    setAutoRetrying(false)

    setRefreshing(state === 'success')
    if (state !== 'success') setState('loading')

    getHistory(limit, controller.signal)
      .then((response) => {
        if (!active) return
        const labelled = response.items.filter((item) => item.status !== 'rejected')
        retryCountRef.current = 0
        setItems(labelled)
        setCount(labelled.length)
        setError(null)
        setAutoRetrying(false)
        setState('success')
        setLastLoadedAt(new Date())
      })
      .catch((caught) => {
        if (!active || isAbortError(caught)) return
        const friendly = describeApiError(caught, 'history')
        setError(friendly)
        setState('error')
        setLastLoadedAt(new Date())

        if (friendly.retryable && retryCountRef.current < MAX_AUTO_RETRIES) {
          const attempt = retryCountRef.current + 1
          retryCountRef.current = attempt
          const delay = Math.min(RETRY_BASE_MS * 2 ** (attempt - 1), RETRY_MAX_MS)
          setAutoRetrying(true)
          retryTimerRef.current = window.setTimeout(() => {
            retryTimerRef.current = null
            if (active) setReloadToken((token) => token + 1)
          }, delay)
        }
      })
      .finally(() => {
        if (active) setRefreshing(false)
      })

    return () => {
      active = false
      controller.abort()
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
    }
    // `state` is intentionally read to avoid a loading flash on refresh; it must
    // not re-trigger the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, reloadToken])

  const clear = useCallback(async (): Promise<number | null> => {
    setClearing(true)
    setClearError(null)
    try {
      const response = await deleteHistory()
      retryCountRef.current = 0
      setItems([])
      setCount(0)
      setState('success')
      setError(null)
      setAutoRetrying(false)
      setLastLoadedAt(new Date())
      return response.deleted
    } catch (caught) {
      if (!isAbortError(caught)) {
        setClearError(describeApiError(caught, 'history'))
      }
      return null
    } finally {
      setClearing(false)
    }
  }, [])

  return {
    items,
    count,
    state,
    error,
    refreshing,
    lastLoadedAt,
    autoRetrying,
    reload,
    clear,
    clearing,
    clearError,
  }
}
