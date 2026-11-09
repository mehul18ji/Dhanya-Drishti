import { useCallback, useEffect, useRef, useState } from 'react'

import { getModelInfo } from '../services/api'
import type { ModelInfoResponse } from '../types/api'
import { describeApiError, isAbortError } from '../utils/errors'
import type { FriendlyError } from '../utils/errors'

export type ModelInfoState = 'loading' | 'success' | 'error'

export interface ModelInfoResult {
  state: ModelInfoState
  info: ModelInfoResponse | null
  error: FriendlyError | null
  /** A retry is scheduled; the page needs no user action. */
  autoRetrying: boolean
  reload: () => void
}

const RETRY_BASE_MS = 4_000
const RETRY_MAX_MS = 30_000
const MAX_AUTO_RETRIES = 6

/**
 * Load the loaded bundle's provenance from `/api/v1/model-info`.
 *
 * Free hosting can put the backend to sleep. Transport and gateway failures are
 * retried with backoff so the model card appears on its own once the service
 * wakes, instead of leaving the visitor stuck on a Retry button.
 */
export function useModelInfo(): ModelInfoResult {
  const [state, setState] = useState<ModelInfoState>('loading')
  const [info, setInfo] = useState<ModelInfoResponse | null>(null)
  const [error, setError] = useState<FriendlyError | null>(null)
  const [autoRetrying, setAutoRetrying] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<number | null>(null)

  const reload = useCallback(() => {
    retryCountRef.current = 0
    setReloadToken((token) => token + 1)
  }, [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setState('loading')
    setAutoRetrying(false)

    getModelInfo(controller.signal)
      .then((response) => {
        if (!active) return
        retryCountRef.current = 0
        setInfo(response)
        setError(null)
        setAutoRetrying(false)
        setState('success')
      })
      .catch((caught) => {
        if (!active || isAbortError(caught)) return
        const friendly = describeApiError(caught, 'model')
        setInfo(null)
        setError(friendly)
        setState('error')

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

    return () => {
      active = false
      controller.abort()
      if (retryTimerRef.current !== null) {
        window.clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
    }
  }, [reloadToken])

  return { state, info, error, autoRetrying, reload }
}
