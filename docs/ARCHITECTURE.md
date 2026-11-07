# DhanyaDrishti — Architecture

> System diagram and component boundaries for Version 1. Reflects the Phase 0 foundation
> plus the Phases 1–4 implementation so far, and the planned structure from
> `PRD.txt` §13, §14 and §17.

---

## 1. Context

```text
User browser
    │  upload one rice-leaf image
    ▼
React dashboard (Vite, TS, Tailwind)              http://localhost:5173
    │  multipart/form-data  POST /api/v1/predict
    ▼
FastAPI backend (Python 3.11)                     http://localhost:8000
    │
    ├── upload validation  → type / size / decode / EXIF
    ├── preprocessing      → aspect-preserving resize, letterbox, denoise
    ├── leaf segmentation  → HSV+Lab + K-Means + morphology → primary leaf
    ├── lesion segmentation→ lesion mask inside the leaf mask
    ├── feature extraction → colour + GLCM + shape + lesion + spatial (versioned)
    ├── inference          → best of SVM / Random Forest / KNN (loaded at startup)
    ├── severity           → experimental lesion-area thresholds
    └── history            → SQLite + temporary artifacts (wiped at restart)
    ▼
Typed JSON response: predicted | uncertain | rejected
```

## 2. Backend component boundaries (PRD §13)

```text
FastAPI route
    ↓
Upload validation service      services/upload_validation.py
    ↓
Image preprocessing service    services/preprocessing_service.py → vision/preprocessing.py
    ↓
Leaf segmentation service      vision/leaf_segmentation.py
    ↓
Disease segmentation service   vision/lesion_segmentation.py
    ↓
Feature extraction service     vision/feature_extraction.py
    ↓
Model inference service        services/inference_service.py → artifacts/production/*
    ↓
Severity service               vision/severity.py
    ↓
Temporary history repository   services/history_service.py → db/repositories.py
    ↓
JSON response                  schemas/prediction.py
```

Implementation status:

| Layer | Module | Phase | State |
|---|---|---|---|
| Config / logging / errors | `app/core/*` | 0 | Done |
| Health API | `app/api/routes_health.py` | 0 | Done |
| Dataset audit + frozen splits | `scripts/*`, `data/splits/*` | 1 | Done |
| Health + model-info routes | `app/api/routes_health.py`, `routes_model_info.py` | 4 | Done (M2) |
| Predict / history routes | `app/api/*` | 4 | Not started |
| Upload validation | `app/services/upload_validation.py` | 4 | Done (M3) |
| Upload-to-features orchestration | `app/services/preprocessing_service.py` | 4 | Done (M4) |
| Preprocessing + quality | `app/vision/preprocessing.py`, `quality.py` | 2 | Done |
| Leaf + lesion segmentation | `app/vision/leaf_segmentation.py`, `lesion_segmentation.py` | 2 | Done |
| Pipeline composition + diagnostics | `app/vision/pipeline.py`, `diagnostics.py` | 2 | Done |
| Segmentation audit | `scripts/run_segmentation_audit.py`, `docs/segmentation_audit/` | 2 | Done |
| Feature extraction | `app/vision/feature_extraction.py` | 3 | Done |
| Training / evaluation / artifacts | `app/ml/*`, `scripts/*` | 3 | Done |
| Inference + artifacts | `app/services/inference_service.py`, `app/artifacts/production/` | 3-4 | Done |
| Severity | `app/vision/severity.py` | 4 | Not started |
| SQLite history | `app/db/*`, `app/services/history_service.py` | 4 | Not started |
| Dashboard | `frontend/src/*` | 0 / 5 | Shell only |

## 3. Frontend structure (PRD §14)

```text
App
└── DashboardLayout            components/layout/DashboardLayout.tsx
    ├── Header                 product identity + model badge + health badge
    ├── Navigation             Analyze Leaf · Prediction History · About Model
    └── Footer                 prototype + severity disclaimers
├── AnalyzePage                pages/AnalyzePage.tsx
│   ├── UploadInstructions
│   ├── ImageUploader / ImagePreview
│   ├── AnalysisProgress
│   ├── PredictionResultCard
│   ├── QualityWarningCard
│   └── SegmentationPreviewPanel
├── HistoryPage                pages/HistoryPage.tsx
│   └── PredictionHistoryTable / HistoryItem
└── AboutModelPage             pages/AboutModelPage.tsx
    ├── DatasetSummary
    ├── WorkflowDiagram
    └── LimitationsNotice
```

Phase 0 delivers the layout plus static versions of the three pages. Upload, result cards,
history rows and mask viewers arrive in Phase 5.

## 4. Data and artifact flow

```text
data/raw/rice_leaf_diseases/        (git-ignored originals, never edited)
        │
        ├── scripts/audit_dataset.py      → data/processed/dataset_manifest.csv
        ├── scripts/make_splits.py        → data/splits/{test,cv_folds,split_manifest}.json
        ├── scripts/build_feature_matrix.py → data/processed/features/feature_set_v1.0.0/*
        └── scripts/export_artifacts.py    → backend/app/artifacts/production/*
                                             model_pipeline.joblib
                                             preprocessing.json
                                             feature_schema.json
                                             segmentation_config.json
                                             model_manifest.json
                                             evaluation_report.json
```

Runtime (never permanent):

```text
backend/.runtime/
    ├── history.sqlite3
    └── artifacts/<prediction_id>/{original.png,leaf_mask.png,lesion_mask.png}
```

## 5. Non-negotiable invariants

1. **One feature extractor** serves both training and inference.
2. **Feature schema version** in `feature_schema.json` is validated against the manifest at startup.
3. **All thresholds in YAML** (`backend/configs/`), hashed into the model manifest.
4. **No training inside a request.** Artifacts load once during lifespan startup.
5. **No permanent storage.** Startup wipe + expiry sweep + shutdown cleanup.
6. **No image distortion.** Resize → crop to leaf bbox with margin → proportional resize → letterbox.
7. **Deterministic seeds** for splits, K-Means and Random Forest, recorded in the manifest.
8. **Truthful states only:** `predicted`, `uncertain`, `rejected` — never a fake "healthy" answer.

## 6. Local execution contract (PRD §21)

| Service | URL | Command |
|---|---|---|
| Frontend | http://localhost:5173 | `npm run dev` (in `frontend/`) |
| Backend | http://localhost:8000 | `uvicorn app.main:app --reload --port 8000` (in `backend/`) |
| API docs | http://localhost:8000/docs | — |
| Health | http://localhost:8000/api/v1/health | — |

## 7. Deployment target (PRD §22)

```text
Vercel (static React build, VITE_API_BASE_URL)
        │ HTTPS
        ▼
Render (FastAPI, CPU, artifacts bundled, temporary filesystem)
```

Temporary-storage and cold-start limitations are documented in the UI and in
`docs/DEPLOYMENT.md` (Phase 7).
