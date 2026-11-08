import { useCallback, useEffect, useState } from 'react'

import { getModelInfo } from '../services/api'
import type { ModelInfoResponse } from '../types/api'
import { describeApiError, isAbortError } from '../utils/errors'
import type { FriendlyError } from '../utils/errors'

export type ModelInfoState = 'loading' | 'success' | 'error'

export interface ModelInfoResult {
  state: ModelInfoState
  info: ModelInfoResponse | null
  error: FriendlyError | null
  reload: () => void
}

/** Load the loaded bundle's provenance from `/api/v1/model-info`. */
export function useModelInfo(): ModelInfoResult {
  const [state, setState] = useState<ModelInfoState>('loading')
  const [info, setInfo] = useState<ModelInfoResponse | null>(null)
  const [error, setError] = useState<FriendlyError | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setState('loading')

    getModelInfo(controller.signal)
      .then((response) => {
        if (!active) return
        setInfo(response)
        setError(null)
        setState('success')
      })
      .catch((caught) => {
        if (!active || isAbortError(caught)) return
        setInfo(null)
        setError(describeApiError(caught, 'model'))
        setState('error')
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [reloadToken])

  return { state, info, error, reload }
}
