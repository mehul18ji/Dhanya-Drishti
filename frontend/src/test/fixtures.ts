import type {
  HistoryItem,
  HealthResponse,
  ModelInfoResponse,
  PredictionResponse,
  RejectedResponse,
} from '../types/api'
import { SEVERITY_DISCLAIMER } from '../utils/disclaimers'

export const PREDICTION_ID = '6f0c8a52-3f5b-4a0e-9c4d-2b1f7a8e9d01'

export function makeHealth(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: 'ok',
    model_loaded: true,
    model_version: 'svm-v1.0.0',
    runtime_storage: 'temporary',
    ...overrides,
  }
}

export function makePrediction(
  overrides: Partial<PredictionResponse> = {},
): PredictionResponse {
  return {
    prediction_id: PREDICTION_ID,
    status: 'predicted',
    disease: 'brown_spot',
    decision_scores: {
      bacterial_leaf_blight: -0.42,
      brown_spot: 1.31,
      leaf_smut: 0.18,
    },
    margin: 1.13,
    ranking: ['brown_spot', 'leaf_smut', 'bacterial_leaf_blight'],
    score_kind: 'decision_margin',
    score_note:
      'decision_function values (one-vs-rest margins), not probabilities. A larger value means the model preferred that class; it is not a confidence percentage.',
    lesion_area_percentage: 12.4,
    lesion_reliable: true,
    severity: 'Moderate',
    severity_note: 'Experimental lesion-area estimate.',
    severity_disclaimer: SEVERITY_DISCLAIMER,
    severity_reason_code: null,
    severity_method: 'experimental_lesion_area_thresholds',
    severity_config_version: 'severity-v1',
    severity_config_sha256: 'a'.repeat(64),
    warnings: [],
    rejections: [],
    missing_features: [],
    artifacts: {
      original_url: `/api/v1/history/${PREDICTION_ID}/original`,
      leaf_mask_url: `/api/v1/history/${PREDICTION_ID}/leaf-mask`,
      lesion_mask_url: `/api/v1/history/${PREDICTION_ID}/lesion-mask`,
    },
    model_name: 'svm',
    model_version: 'svm-v1.0.0',
    feature_set_version: '1.0.0',
    segmentation_config_version: 'seg-v2',
    quality_config_version: 'quality-v1',
    stage_ms: { decode_and_working: 41.2, total: 178.4 },
    created_at: '2026-11-08T01:52:26+00:00',
    runtime_storage: 'temporary',
    ...overrides,
  }
}

export function makeRejected(
  overrides: Partial<RejectedResponse> = {},
): RejectedResponse {
  return {
    status: 'rejected',
    reason_code: 'NO_CLEAR_LEAF_FOUND',
    message:
      'No suitable rice leaf region could be detected. Upload one clear, well-lit leaf.',
    runtime_storage: 'temporary',
    ...overrides,
  }
}

export function makeHistoryItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    prediction_id: PREDICTION_ID,
    created_at: '2026-11-08T01:52:26+00:00',
    expires_at: '2026-11-08T02:52:26+00:00',
    status: 'predicted',
    disease: 'brown_spot',
    decision_scores: {
      bacterial_leaf_blight: -0.42,
      brown_spot: 1.31,
      leaf_smut: 0.18,
    },
    margin: 1.13,
    severity: 'Moderate',
    severity_reason_code: null,
    severity_config_version: 'severity-v1',
    lesion_area_percentage: 12.4,
    lesion_reliable: true,
    model_name: 'svm',
    model_version: 'svm-v1.0.0',
    feature_set_version: '1.0.0',
    segmentation_config_version: 'seg-v2',
    quality_config_version: 'quality-v1',
    warnings: [],
    rejections: [],
    missing_features: [],
    stage_ms: { total: 178.4 },
    artifacts: {
      original_url: `/api/v1/history/${PREDICTION_ID}/original`,
      leaf_mask_url: `/api/v1/history/${PREDICTION_ID}/leaf-mask`,
      lesion_mask_url: `/api/v1/history/${PREDICTION_ID}/lesion-mask`,
    },
    ...overrides,
  }
}

export function makeModelInfo(
  overrides: Partial<ModelInfoResponse> = {},
): ModelInfoResponse {
  return {
    model_name: 'svm',
    model_version: 'svm-v1.0.0',
    bundle_version: '1.0.0',
    bundle_exported_at: '2026-11-07T18:58:15+00:00',
    feature_set_version: '1.0.0',
    feature_count: 50,
    classes: ['bacterial_leaf_blight', 'brown_spot', 'leaf_smut'],
    segmentation_config_version: 'seg-v2',
    quality_config_version: 'quality-v1',
    dataset_version: 'ds-cc74ed659044',
    split_protocol: 'v1',
    training_rows: 96,
    cv_macro_f1_mean: 0.8411814329461389,
    cv_macro_f1_std: 0.06037020284815041,
    cv_accuracy_mean: 0.8436842105263157,
    cv_balanced_accuracy_mean: 0.8396825396825397,
    held_out_rows: 24,
    held_out_macro_f1: 0.7854636591478696,
    held_out_accuracy: 0.7916666666666666,
    held_out_status: 'evaluated_once_after_selection_not_recomputed',
    calibrated_probabilities: false,
    score_kind: 'decision_margin',
    score_note:
      'decision_function values (one-vs-rest margins), not probabilities. A larger value means the model preferred that class; it is not a confidence percentage.',
    severity_disclaimer: SEVERITY_DISCLAIMER,
    known_failure_cases: [
      'There is no healthy-leaf class: the model always returns one of the three diseases and must not be presented as a diseased/healthy test.',
      'Segmentation thresholds are calibrated on white-paper studio photographs; noisy or cluttered phone backgrounds are untested.',
    ],
    ...overrides,
  }
}

export function makeFile({
  name = 'leaf.jpg',
  type = 'image/jpeg',
  size = 1024,
}: {
  name?: string
  type?: string
  size?: number
} = {}): File {
  const file = new File([new Uint8Array(Math.min(size, 32))], name, { type })
  if (file.size !== size) {
    Object.defineProperty(file, 'size', { value: size })
  }
  return file
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function errorEnvelope(
  status: number,
  reasonCode: string,
  message: string,
): Response {
  return jsonResponse(
    { status: 'error', reason_code: reasonCode, message },
    status,
  )
}
