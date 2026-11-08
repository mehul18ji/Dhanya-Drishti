/**
 * Typed mirrors of the Phase 4 API contract (`docs/API.md`).
 *
 * Deliberate omissions:
 * - no `confidence` or `probability` field exists, because the served SVM is
 *   uncalibrated (decision P-15/P-18) and exposes decision-function margins only;
 * - `severity` is nullable and must be displayed with `severity_disclaimer`;
 * - a rejected response has no `prediction_id`, no artifacts and no history row.
 */

export type HealthStatus = 'ok'

export interface HealthResponse {
  status: HealthStatus
  model_loaded: boolean
  model_version: string | null
  runtime_storage: 'temporary'
}

export type Severity = 'Mild' | 'Moderate' | 'Severe'
export type PredictionStatus = 'predicted' | 'uncertain'
export type HistoryStatus = PredictionStatus | 'rejected'
export type RuntimeStorage = 'temporary'

/** Temporary artifact URLs relative to the API base (`/api/v1/...`). */
export interface ArtifactLinks {
  original_url: string | null
  leaf_mask_url: string | null
  lesion_mask_url: string | null
}

/** `POST /api/v1/predict` — HTTP 200 with a supported disease label. */
export interface PredictionResponse {
  prediction_id: string
  status: PredictionStatus
  disease: string
  decision_scores: Record<string, number>
  /** Best minus second-best decision score — not a confidence value. */
  margin: number
  ranking: string[]
  score_kind: 'decision_margin'
  score_note: string
  lesion_area_percentage: number | null
  lesion_reliable: boolean
  severity: Severity | null
  severity_note: string
  severity_disclaimer: string
  severity_reason_code: string | null
  severity_method: string
  severity_config_version: string
  severity_config_sha256: string
  warnings: string[]
  rejections: string[]
  missing_features: string[]
  artifacts: ArtifactLinks
  model_name: string
  model_version: string
  feature_set_version: string
  segmentation_config_version: string
  quality_config_version: string
  stage_ms: Record<string, number>
  created_at: string
  runtime_storage: RuntimeStorage
}

/** `POST /api/v1/predict` — HTTP 200 but the image could not be analysed. */
export interface RejectedResponse {
  status: 'rejected'
  reason_code: string
  message: string
  runtime_storage: RuntimeStorage
}

export type PredictResponse = PredictionResponse | RejectedResponse

/** Typed error envelope returned for 413 / 415 / 422 / 503 and other failures. */
export interface ErrorEnvelope {
  status: 'error'
  reason_code: string
  message: string
}

/** `GET /api/v1/history` item. Score fields are margins, never probabilities. */
export interface HistoryItem {
  prediction_id: string
  created_at: string
  expires_at: string
  status: HistoryStatus
  disease: string | null
  decision_scores: Record<string, number>
  margin: number | null
  severity: Severity | null
  severity_reason_code: string | null
  severity_config_version: string
  lesion_area_percentage: number | null
  lesion_reliable: boolean
  model_name: string
  model_version: string
  feature_set_version: string
  segmentation_config_version: string
  quality_config_version: string
  warnings: string[]
  rejections: string[]
  missing_features: string[]
  stage_ms: Record<string, number>
  artifacts: ArtifactLinks
}

export interface HistoryListResponse {
  count: number
  items: HistoryItem[]
  runtime_storage: RuntimeStorage
}

export interface HistoryDeleteResponse {
  deleted: number
  runtime_storage: RuntimeStorage
}

/** `GET /api/v1/model-info` — read from the loaded bundle manifest. */
export interface ModelInfoResponse {
  model_name: string
  model_version: string
  bundle_version: string
  bundle_exported_at: string
  feature_set_version: string
  feature_count: number
  classes: string[]
  segmentation_config_version: string
  quality_config_version: string
  dataset_version: string
  split_protocol: string
  training_rows: number
  cv_macro_f1_mean: number
  cv_macro_f1_std: number
  cv_accuracy_mean: number
  cv_balanced_accuracy_mean: number
  held_out_rows: number
  held_out_macro_f1: number
  held_out_accuracy: number
  held_out_status: string
  calibrated_probabilities: boolean
  score_kind: string
  score_note: string
  severity_disclaimer: string
  known_failure_cases: string[]
}
