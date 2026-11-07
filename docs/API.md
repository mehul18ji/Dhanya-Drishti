# DhanyaDrishti — API reference (Phase 4)

Base URL locally: `http://localhost:8000` · OpenAPI: `/docs`, `/redoc`, `/openapi.json`.

Academic prototype: three diseased rice-leaf classes only (Bacterial Leaf Blight,
Brown Spot, Leaf Smut). There is **no healthy class**, nothing is permanent, and
severity is an experimental visible-lesion-area estimate.

> All endpoints are `/api/v1/*`. The API never retrains, never calibrates and never
> reads the held-out test rows.

---

## 1. Temporary-storage rules (applies to every endpoint)

| Rule | Behaviour |
|---|---|
| Storage location | `RUNTIME_DIR` (`backend/.runtime` by default): `history.sqlite3` + `artifacts/<uuid>/` |
| Lifetime | Wiped at backend startup, at graceful shutdown, after `HISTORY_EXPIRY_MINUTES` (default 60), or on `DELETE /api/v1/history` |
| Persistence | Never promised across restarts, redeploys, server sleep or expiry |
| Images | Uploaded originals and masks are deleted with their row; nothing is sent to cloud storage |
| Ids | Every prediction id is a canonical UUID; artifact paths are derived from the re-serialised UUID, so a crafted id cannot traverse the filesystem |
| Rejected uploads | Post-pipeline rejections are **not** stored: no id, no artifacts, no history row |

---

## 2. `GET /api/v1/health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "svm-v1.0.0",
  "runtime_storage": "temporary"
}
```

`model_loaded` is `false` (and `model_version` `null`) when the verified bundle
could not be loaded; the process still serves `/health` and answers model-dependent
endpoints with `503 MODEL_NOT_LOADED`.

## 3. `GET /api/v1/model-info`

Describes the **loaded** bundle only — read from `model_manifest.json`, never
recomputed: model/bundle versions, feature-set version and count, the three
classes, pinned `seg-v2` / `quality-v1` versions, dataset version, split protocol,
development rows, CV macro F1 ± std, the single already-consumed held-out result,
`calibrated_probabilities: false`, `score_kind: "decision_margin"`, the severity
disclaimer and known failure cases.

---

## 4. `POST /api/v1/predict`

`Content-Type: multipart/form-data`, field `file` (JPG / JPEG / PNG / WEBP).

### Success — `predicted` or `uncertain`

```json
{
  "prediction_id": "6f0c…-uuid",
  "status": "predicted",
  "disease": "brown_spot",
  "decision_scores": {"bacterial_leaf_blight": -0.42, "brown_spot": 1.31, "leaf_smut": 0.18},
  "margin": 1.13,
  "ranking": ["brown_spot", "leaf_smut", "bacterial_leaf_blight"],
  "score_kind": "decision_margin",
  "score_note": "decision_function values (one-vs-rest margins), not probabilities. …",
  "lesion_area_percentage": 12.4,
  "lesion_reliable": true,
  "severity": "Moderate",
  "severity_note": "Experimental lesion-area estimate.",
  "severity_disclaimer": "Severity is an experimental estimate based on the visible lesion area in this image. It is not a validated agronomic severity grade.",
  "severity_reason_code": null,
  "severity_method": "experimental_lesion_area_thresholds",
  "severity_config_version": "severity-v1",
  "severity_config_sha256": "…",
  "warnings": [],
  "rejections": [],
  "missing_features": [],
  "artifacts": {
    "original_url": "/api/v1/history/<id>/original",
    "leaf_mask_url": "/api/v1/history/<id>/leaf-mask",
    "lesion_mask_url": "/api/v1/history/<id>/lesion-mask"
  },
  "model_name": "svm",
  "model_version": "svm-v1.0.0",
  "feature_set_version": "1.0.0",
  "segmentation_config_version": "seg-v2",
  "quality_config_version": "quality-v1",
  "stage_ms": {"decode_and_working": 41.2, "total": 178.4},
  "created_at": "2026-11-08T01:52:26+00:00",
  "runtime_storage": "temporary"
}
```

Rules the client must respect:

- **Decision scores are not confidence.** They are `decision_function` margins.
  There is no `confidence` or `probability` field, and no score threshold is applied
  while decision P-05 is open.
- `status: "uncertain"` means the label is **not confirmed** (quality warning,
  unreliable lesion, missing severity, or an extracted-vector warning). Show the
  uncertainty notice from PRD §11; never present it as a diagnosis.
- `severity` is `null` when the lesion area is unreliable, missing or invalid
  (`severity_reason_code` says which). It is never inferred as `Mild`/`0 %`.
- `artifacts` URLs point at temporary files; they 404 once the row expires.

### Rejection — `200` + `status: "rejected"`

Returned when the image reaches the vision pipeline but cannot be analysed
(no clear leaf, too dark, too blurry, …):

```json
{
  "status": "rejected",
  "reason_code": "NO_CLEAR_LEAF_FOUND",
  "message": "No suitable rice leaf region could be detected. Upload one clear, well-lit leaf.",
  "runtime_storage": "temporary"
}
```

No `prediction_id`, no artifacts, no history row. `NO_CLEAR_LEAF_FOUND` is preferred
when present; otherwise the first rejection code is reported.

### Upload-level failures — typed error envelope

```json
{"status": "error", "reason_code": "FILE_TOO_LARGE", "message": "…"}
```

| Status | `reason_code` | Cause |
|---|---|---|
| 413 | `FILE_TOO_LARGE` | Upload exceeds `MAX_UPLOAD_MB` |
| 415 | `UNSUPPORTED_FILE_TYPE` | Disallowed extension or real format / extension spoof |
| 422 | `INVALID_UPLOAD` | Empty, unreadable or corrupt image |
| 422 | `IMAGE_TOO_SMALL` | Below the hard dimension limits |
| 503 | `MODEL_NOT_LOADED` | Production bundle unavailable (checked before any decoding) |

---

## 5. `GET /api/v1/history`

`limit` (1–200, default 50). Expired rows are swept before the response.

```json
{
  "count": 1,
  "items": [
    {
      "prediction_id": "6f0c…",
      "created_at": "2026-11-08T01:52:26+00:00",
      "expires_at": "2026-11-08T02:52:26+00:00",
      "status": "uncertain",
      "disease": "leaf_smut",
      "decision_scores": {"…": 0.0},
      "margin": 0.31,
      "severity": "Mild",
      "severity_reason_code": null,
      "severity_config_version": "severity-v1",
      "lesion_area_percentage": 8.2,
      "lesion_reliable": true,
      "model_name": "svm",
      "model_version": "svm-v1.0.0",
      "feature_set_version": "1.0.0",
      "segmentation_config_version": "seg-v2",
      "quality_config_version": "quality-v1",
      "warnings": ["FULL_FRAME_FALLBACK"],
      "rejections": [],
      "missing_features": [],
      "stage_ms": {"total": 178.4},
      "artifacts": {
        "original_url": "/api/v1/history/6f0c…/original",
        "leaf_mask_url": "/api/v1/history/6f0c…/leaf-mask",
        "lesion_mask_url": "/api/v1/history/6f0c…/lesion-mask"
      }
    }
  ],
  "runtime_storage": "temporary"
}
```

Only results that carry a disease label are stored (`predicted` and `uncertain`);
rejected uploads never appear here.

## 6. `GET /api/v1/history/{prediction_id}`

One row, same shape as a list item. Unknown, expired or malformed ids:

| Status | `reason_code` | Cause |
|---|---|---|
| 404 | `PREDICTION_NOT_FOUND` | Unknown or expired prediction |
| 422 | `INVALID_UPLOAD`/validation | Not a UUID (rejected by FastAPI) |

## 7. Artifact routes

| Route | Returns |
|---|---|
| `GET /api/v1/history/{id}/original` | Oriented uploaded image, `image/png` |
| `GET /api/v1/history/{id}/leaf-mask` | Detected leaf mask, `image/png` |
| `GET /api/v1/history/{id}/lesion-mask` | Lesion mask inside the leaf, `image/png` |

Unknown id, expired row or a missing file → `404 ARTIFACT_NOT_FOUND`.

## 8. `DELETE /api/v1/history`

```json
{"deleted": 3, "runtime_storage": "temporary"}
```

Removes every history row **and** every artifact file immediately.

---

## 9. Limits and honesty guarantees

- CPU-only; one image per request; the heavy work runs in a worker thread, so the
  event loop stays responsive.
- Request logging records the pipeline time and the total request time per
  prediction.
- No accounts, no permanent storage, no cloud storage, no treatment advice.
- The service never claims a leaf is healthy: the possible statuses are
  `predicted`, `uncertain`, `rejected`.
- The model is the committed `svm-v1.0.0` bundle; the API never trains or
  recalibrates.
