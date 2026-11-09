# DhanyaDrishti — Agent Handoff

> Read this first if you are a new human or AI-agent session. It encodes the PRD §24
> continuity protocol so no prior chat history is required.

---

## 1. Mandatory beginning-of-session procedure

1. Read `PRD.txt` (or `docs/PRD.md`).
2. Read `docs/DECISIONS.md`.
3. Read `PROJECT_STATUS.md`.
4. Read `PHASE_PLAN.txt` — only the section for the current phase is usually needed.
5. Inspect the repository state:
   ```powershell
   git status
   git log --oneline -10
   ```
6. Run the relevant existing tests **before** changing code:
   ```powershell
   cd backend; python -m pytest -q
   cd ..\frontend; npm test; npm run build
   ```
7. Continue only from the **"Next exact task"** in `PROJECT_STATUS.md`.
8. Do not replace completed work or change a locked decision (see `docs/DECISIONS.md` §1).

If `PROJECT_STATUS.md` and reality disagree, trust reality, then fix the status file.

## 2. Mandatory end-of-session procedure

1. Run the relevant tests.
2. Update `PROJECT_STATUS.md` (all fields, including the next exact task).
3. Update documentation if architecture or behaviour changed.
4. Record known limitations or blockers.
5. Commit only after tests pass, with a focused message
   (e.g. `feat(api): health endpoint and typed config`).
6. Leave exactly one clearly stated next task.

## 3. Repository map (where things belong)

| Need | Location |
|---|---|
| Product requirements | `PRD.txt`, `docs/PRD.md` |
| Execution plan | `PHASE_PLAN.txt` |
| Current state | `PROJECT_STATUS.md` |
| API reference (endpoints, errors, storage) | `docs/API.md` |
| Locked decisions | `docs/DECISIONS.md` |
| System design | `docs/ARCHITECTURE.md` |
| Dataset audit, duplicates, splits | `docs/DATASET_AUDIT.md`, `data/splits/` |
| Phase 2 segmentation evidence | `docs/SEGMENTATION_NOTES.md`, `docs/segmentation_audit/` |
| Backend app | `backend/app/` |
| Calibration thresholds (Phase 2+) | `backend/configs/*.yaml` |
| Production model artifacts | `backend/app/artifacts/production/` |
| Runtime temp storage (wiped) | `backend/.runtime/` |
| Backend tests | `backend/tests/` |
| Frontend app | `frontend/src/` |
| Dataset (not committed) | `data/raw/rice_leaf_diseases/` |
| Split manifests (committed) | `data/splits/` |
| Experiment notebooks | `notebooks/` |
| One-off scripts | `scripts/` |
| Cross-stack tests | `tests/end_to_end/` |

## 4. Local commands

```powershell
# Backend (from repository root)
cd backend
python -m pytest -q
uvicorn app.main:app --reload --port 8000

# Frontend (from repository root)
cd frontend
npm install
npm run dev          # http://localhost:5173
npm test             # Vitest + jsdom + Testing Library
npm run typecheck
npm run build        # type-check + production build

# Dataset audit + frozen splits (from repository root)
python scripts/audit_dataset.py
python scripts/find_near_duplicates.py
python scripts/build_duplicate_groups.py
python scripts/make_splits.py
python scripts/make_splits.py --verify
python -m pytest tests -q

# Phase 2 segmentation audit + committed evidence set (from repository root)
python scripts/run_segmentation_audit.py
python scripts/run_segmentation_audit.py --only leaf_smut --limit 5   # quick spot-check
python scripts/run_segmentation_audit.py --no-panels --no-curated     # numbers only

# Local acceptance (real backend + real dataset images; writes evidence JSON)
python scripts/run_local_acceptance.py
python scripts/check_restart_cleanup.py
```

Environment:

- Root `.env` (copy of `.env.example`) → backend settings.
- `frontend/.env` (copy of `frontend/.env.example`) → `VITE_API_BASE_URL`.

## 5. Current state (Phases 1–6 complete; Phase 7 deployment not started)

- Backend: app factory, typed settings, logging, error mapping, CORS, health endpoint,
  `GET /api/v1/model-info`, upload validation, the artifact-backed inference service and the
  upload-to-features preprocessing orchestration.
- Frontend: dashboard shell (header/nav/footer), three routed pages, health badge, API client stub.
- Data: raw dataset in `data/raw/rice_leaf_diseases/` (40/40/40), git-ignored.
- Audit: manifest + summary generated; dataset version `ds-cc74ed659044`.
- Duplicates: 13 confirmed groups (27 images) recorded in `data/splits/duplicate_groups.json`.
- Splits: frozen v1 — 24-image singleton-only test (8/class) + group-aware stratified
  5-fold CV over 96 images; seed 42; reproducible via `scripts/make_splits.py --verify`.
- Vision pipeline (`backend/app/vision/`): config (`seg-v2`, `quality-v1`), preprocessing,
  quality, leaf segmentation, lesion segmentation, `pipeline.py` orchestration,
  `feature_extraction.py` (feature set `1.0.0`, 50 ordered features) and
  `diagnostics.py` panels. All thresholds live in `backend/configs/*.yaml`.
- Phase 2 audit: 120/120 plausible leaf masks (dev 96/96, held-out test 24/24),
  0 rejected, 33 uncertain, 8 full-frame fallbacks, 130.6 ms mean per image on CPU.
  Evidence: `docs/SEGMENTATION_NOTES.md`, `docs/segmentation_audit/` (12 curated panels).
- Phase 3: split-aware 120-row feature matrix (`scripts/build_feature_matrix.py`), local CPU
  SVM/RF/KNN comparison with fold-local imputation (`backend/app/ml/training.py`), the
  evaluation report with honest baselines (`backend/app/ml/evaluation.py`) and the committed
  production bundle (`backend/app/artifacts/production/`, `scripts/export_artifacts.py`,
  model `svm-v1.0.0`). Selection used development CV only; the held-out test was scored once
  (macro F1 0.7855 vs CV 0.8412).
- Phase 4 so far: M1 inference service (hash/schema/config-verified bundle, decision-margin
  scores that are never described as probabilities), M2 lifespan wiring + truthful `/health`
  + `model-info`, M3 upload validation, M4 `services/preprocessing_service.py` (validated upload
  -> decode -> segmentation -> 50-feature vector, with `predicted` / `uncertain` / `rejected`
  mapping, a model-first 503 gate and schema/config provenance refusal), M5 `vision/severity.py`
  + `configs/severity.yaml` (`severity-v1`: <10 % Mild, 10–<25 % Moderate, ≥25 % Severe; `None`
  with a reason code for an unreliable, missing or invalid lesion area; PRD §12 disclaimer
  verbatim, config version + SHA-256 on every result), M6 `services/prediction_service.py`
  (validated upload -> preprocessing -> inference -> severity in one `PredictionResult` with a
  `prediction_id`, decision-margin scores that are never confidence, rejected = no label/score/
  severity, and no persistence), M7 `db/history_repository.py` + `services/image_artifact_service.py`
  + `services/history_service.py` (UUID-keyed SQLite rows and temporary PNG artifacts under
  `RUNTIME_DIR`, expiry sweep, startup wipe, shutdown cleanup, delete removes rows **and** files),
  M8 `POST /api/v1/predict` (`api/routes_predict.py`, `schemas/prediction.py`: worker-thread
  composition, JSON-safe predicted/uncertain body, 200 `rejected` body with no id, typed
  413/415/422/503, logged timings) and M9 history/artifact routes + `DELETE /api/v1/history`
  (`api/routes_history.py`, `schemas/history.py`, `docs/API.md`).
- Phase 5 complete: typed client (`services/api.ts`, `types/api.ts`, API-relative artifact
  URLs, timeouts, typed 413/415/422/503/network errors), `useHealth` cold-start badge,
  upload/preview/analyze flow with approximate staged progress, predicted/uncertain/
  rejected/upload-error/model-unavailable cards, decision-margin score panel (never
  confidence), severity disclaimer + lesion reliability gates, warnings/missing features,
  temporary artifact thumbnails, history table with warning details + confirmation clear,
  and the About Model card from `/api/v1/model-info`. Honesty rules and the state matrix are
  documented in `docs/FRONTEND.md`.
- Phase 5 tests: 13 frontend files / 64 Vitest tests green; `npm run typecheck` and
  `npm run build` clean. Backend remained 217 tests + 6 split invariants at Phase 5 close (222
  after the 2026-11-09 final audit), all green. A live
  smoke test against a real backend verified prediction, artifacts, 200 rejection not stored,
  413/415/422, history delete and artifact 404 after delete.
- Local acceptance correction (2026-11-09): the previous "restart did not clear history"
  finding was a harness defect, not an application defect. Startup cleanup was proven with two
  real processes sharing one `RUNTIME_DIR` (8 rows + 24 files → 0 rows + 0 files, old URLs 404).
  Both Playwright configs now use backend `reuseExistingServer: false`, and
  `backend/tests/test_restart_cleanup.py` (3 tests) pins startup cleanup. The full 38-check
  matrix and its evidence live in `docs/LOCAL_ACCEPTANCE_REPORT.md` and
  `docs/local_acceptance/api_evidence.json`.
- Final localhost-release audit (2026-11-09): the acceptance evidence-path reporting bug is
  fixed (`scripts/run_local_acceptance.py` accepts an external `--evidence` path safely) and
  pinned by `backend/tests/test_local_acceptance_reporting.py` (2 tests). The 14 snapshots under
  `data/processed/reproducibility/` are tracked; `demo_images/` holds four documented UI-only
  examples; disposable caches/reports/runtimes were moved to a dated quarantine outside the repo.
- Tests: 64 frontend + 222 backend (`backend/`) + 6 split invariants (root `tests/`),
  22 Playwright dev tests (Chrome + Edge) + 11 Playwright production-preview tests, plus the
  38-check local acceptance matrix.

## 6. Rules that prevent damage

- Environment and tooling: the required classical ML pipeline runs locally on CPU through versioned Python scripts. Google Colab is out of scope for the required workflow; local Jupyter notebooks are optional exploration tools only.

- Do not edit or delete files under `data/raw/`.
- Do not commit raw images, `.env`, SQLite files or `backend/.runtime/`.
- Do not add TensorFlow, CUDA or MobileNetV2 to Version 1.
- Do not train a model inside a request handler.
- Do not duplicate feature-extraction logic; training and inference must share one module.
- Keep every numeric threshold in `backend/configs/*.yaml`.
- Never claim healthy-leaf detection; return `uncertain` instead.
- Keep the exact disclaimer wording from the PRD in API responses and UI.
- The dashboard must never display a confidence/probability percentage: scores are
  `decision_function` margins only (P-15/P-18/P-19).
- Never turn an unreliable/missing lesion measurement into `0 %` or `Mild`; show
  “Not available”/“Not reported” with the reason (P-22).
- A 200 `rejected` result and every upload-level error stay out of history; do not style
  them as predictions (P-16/P-20/P-24).
- Do not add runtime frontend dependencies without a decision; the test toolchain is
  dev-only (P-25).
- Never claim a restart/cleanup pass from a server you did not start. An existing listener on
  `:8000` keeps its old `RUNTIME_DIR`; prove the old PID exited and the port closed (see
  `scripts/check_restart_cleanup.py`). Playwright must keep backend `reuseExistingServer: false`.
- Do not weaken the restart requirement: shutdown cleanup is best-effort on a hard kill, so
  startup wipe (`HistoryService.start_fresh()` in the lifespan) is the guarantee that must stay
  tested.

## 7. Handoff checklist for the next session

- [ ] Read the five documents listed in §1.
- [ ] Confirm tests pass before edits (`npm test`, `npm run build`, backend `pytest -q`).
- [ ] Pick up the "Next exact task" from `PROJECT_STATUS.md`.
- [ ] Phase 6 and local acceptance are complete; do not start Phase 7 (deployment) without explicit user approval.
- [ ] Stay inside the current phase; do not start the next phase early.
- [ ] Update `PROJECT_STATUS.md` before finishing.
