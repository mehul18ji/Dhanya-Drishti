import type { HealthResponse } from '../types/api'

/** Backend base URL comes from VITE_API_BASE_URL (PRD §21). */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

/** GET /api/v1/health */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/v1/health', signal)
}
