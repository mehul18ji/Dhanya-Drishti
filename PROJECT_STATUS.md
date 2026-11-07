# PROJECT STATUS

> Required by PRD §24. Update at the end of every working session.
> Format is fixed — keep the labels exactly as written.

Current phase: Phase 0 — Repository foundation (complete)
Last completed task: Phase 0 scaffold — docs set, backend health API with typed config, frontend dashboard shell (routing + layout + three pages), env templates, .gitignore, dataset moved to data/raw/ and git-ignored.
Tests last run: 2026-11-07 — `python -m pytest -q` in `backend/` (3 tests) and `npm run build` in `frontend/`.
Test result: Backend 3 passed. Frontend type-check + production build passed.
Current branch: main
Latest commit: 14602fb (merge commit; Phase 0 work is uncommitted at the time of writing)
What works:
- Backend starts with `uvicorn app.main:app --reload --port 8000`; `/docs` and `/openapi.json` are served.
- `GET /api/v1/health` returns `{status: ok, model_loaded: false, model_version: null, runtime_storage: temporary}`.
- CORS allowlist is read from `CORS_ORIGINS` (defaults to localhost:5173 / 127.0.0.1:5173).
- Typed settings via pydantic-settings, structured logging, `AppError` → JSON error mapping.
- Frontend builds and serves at `http://localhost:5173` with header, navigation, footer and three routes (`/`, `/history`, `/about`).
- Header shows live backend status by calling `/api/v1/health`; shows "no model yet" while `model_loaded` is false.
- All PRD disclaimers are present in the shell (upload notice, severity note, footer, About Model).
- Dataset is at `data/raw/rice_leaf_diseases/` (40/40/40) and excluded from git.
What does not work:
- No image upload, prediction, segmentation, feature extraction or model — by design (Phases 1-5).
- No prediction history storage/API yet; the history page is an empty state.
- No `/api/v1/model-info` endpoint yet (Phase 4).
- No dataset audit script, split manifests or notebooks yet (Phase 1).
- No scikit-image installed yet; required from Phase 3.
Next exact task: Start Phase 1 — write `scripts/audit_dataset.py` to emit `data/processed/dataset_manifest.csv` (path, class, width, height, aspect, bytes, md5, decode_ok, exif_orientation), then confirm 40/40/40 and log the 9 tiny + 13 close-up images.
Known blockers: None.
Decisions that must not be changed:
- Only the 120-image, 3-class dataset; no healthy class.
- Classical workflow only; SVM/RF/KNN compared; winner chosen by macro F1.
- React + Vite + Tailwind + TypeScript frontend; Python 3.11 + FastAPI backend; OpenCV + scikit-learn.
- SQLite/temp files only, wiped at startup; no permanent image storage.
- CPU-only; no TensorFlow/CUDA/MobileNetV2 in Version 1.
- Severity is an experimental lesion-area estimate with its disclaimer.
