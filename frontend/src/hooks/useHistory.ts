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
  reload: () => void
  clear: () => Promise<number | null>
  clearing: boolean
  clearError: FriendlyError | null
}

/**
 * Temporary history client.
 *
 * Only labelled results are stored by the backend, so any defensive `rejected`
 * row is filtered out rather than displayed as a diagnosis.
 */
export function useHistory(limit = 50): HistoryState {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [count, setCount] = useState(0)
  const [state, setState] = useState<HistoryLoadState>('loading')
  const [error, setError] = useState<FriendlyError | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [clearing, setClearing] = useState(false)
  const [clearError, setClearError] = useState<FriendlyError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    controllerRef.current = controller

    setRefreshing(state === 'success')
    if (state !== 'success') setState('loading')

    getHistory(limit, controller.signal)
      .then((response) => {
        if (!active) return
        const labelled = response.items.filter((item) => item.status !== 'rejected')
        setItems(labelled)
        setCount(labelled.length)
        setError(null)
        setState('success')
        setLastLoadedAt(new Date())
      })
      .catch((caught) => {
        if (!active || isAbortError(caught)) return
        setError(describeApiError(caught, 'history'))
        setState('error')
        setLastLoadedAt(new Date())
      })
      .finally(() => {
        if (active) setRefreshing(false)
      })

    return () => {
      active = false
      controller.abort()
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
      setItems([])
      setCount(0)
      setState('success')
      setError(null)
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
    reload,
    clear,
    clearing,
    clearError,
  }
}
