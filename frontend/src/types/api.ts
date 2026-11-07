/**
 * Typed API contract shared by the dashboard (PRD §15).
 * Only the endpoints implemented so far are declared; the prediction
 * contract is added in Phase 4-5.
 */

export type HealthStatus = 'ok'

export interface HealthResponse {
  status: HealthStatus
  model_loaded: boolean
  model_version: string | null
  runtime_storage: 'temporary'
}
