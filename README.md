# DhanyaDrishti

Academic prototype dashboard for **rice-leaf disease analysis** using a fully **classical**
computer-vision and machine-learning pipeline (no deep learning in Version 1).

Upload one photograph of a diseased rice leaf and receive:

- a predicted disease label — **Bacterial Leaf Blight**, **Brown Spot** or **Leaf Smut**;
- per-class **decision-function margins** and a best-vs-second margin (**not** a confidence or
  probability percentage);
- a lesion-area estimate;
- an *experimental* severity estimate (Mild / Moderate / Severe);
- quality and uncertainty warnings when the result is unreliable;
- temporary prediction history for the current backend session.

> ⚠ This prototype supports only three diseased rice-leaf categories. Do not upload healthy
> leaves. Results are academic estimates and must not be used as professional agricultural advice.

---

## Status

**Current phase: Phase 6 — Integration, QA, model card: COMPLETE. Phase 7 (deployment) is next and has not started.**

| Area | State |
|---|---|
| Repository foundation, docs, env templates | Done |
| Frontend dashboard shell (routing, layout, pages) | Done |
| Backend health API + typed config | Done |
| Dataset audit and reproducible splits | Done (Phase 1) |
| Classical CV pipeline (preprocessing, quality, leaf + lesion segmentation, audit) | Done (Phase 2) |
| Features + SVM/RF/KNN comparison, production model bundle | Done (Phase 3) |
| Inference service, lifespan load, `/health`, `/model-info`, upload validation, preprocessing orchestration, experimental severity, prediction composition | Done (Phase 4 M1–M6) |
| `POST /predict`, temporary history, artifact serving, API docs | Done (Phase 4 M7–M9) |
| Typed frontend API client, upload/preview/analyze flow, result states, history, About Model, component tests | Done (Phase 5 M1–M7) |
| QA, real-browser E2E, model card | Complete (Phase 6) |
| Deployment | Not started (Phase 7) |

The full phase-by-phase plan lives in [`PHASE_PLAN.txt`](./PHASE_PLAN.txt).
Living status lives in [`PROJECT_STATUS.md`](./PROJECT_STATUS.md).

## Repository layout

```text
DhanyaDrishti/
├── PRD.txt                  approved product requirements (authority)
├── PHASE_PLAN.txt           detailed phase-wise execution plan
├── PROJECT_STATUS.md        current state and next exact task
├── docs/                    PRD, decisions, architecture, handoff
├── frontend/                React + Vite + TypeScript + Tailwind
├── backend/                 FastAPI application, configs, tests, artifacts
├── data/                    raw (git-ignored), processed, splits
├── demo_images/             curated UI-only demo images + provenance README
├── notebooks/               dataset audit, segmentation, model comparison
├── scripts/                 audit / split / train / evaluate / export
└── tests/end_to_end/        cross-stack tests
```

## Prerequisites

- Python 3.11+
- Node.js 20+ (LTS) and npm
- Git

## Backend — setup and run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>
- Tests: `python -m pytest`

Expected health response when the production bundle is loaded:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "svm-v1.0.0",
  "runtime_storage": "temporary"
}
```

## Frontend — setup and run

```powershell
cd frontend
npm install
npm run dev
```

- Dashboard: <http://localhost:5173>
- Build check: `npm run build`
- Type check: `npm run typecheck`
- Component/API tests: `npm test` (Vitest + jsdom + Testing Library)
- Real-browser E2E: `cd tests/end_to_end && npx playwright test` (dev server, Chrome + Edge)
- Production-preview E2E: `cd tests/end_to_end && npx playwright test --config=playwright.preview.config.ts` (built bundle)
- E2E headed: `cd tests/end_to_end && npx playwright test --headed`

## Local acceptance (real backend, real dataset images)

```powershell
python scripts/run_local_acceptance.py      # 38-check matrix, writes docs/local_acceptance/api_evidence.json
python scripts/check_restart_cleanup.py     # two real processes, same RUNTIME_DIR
```

Both commands start their own `uvicorn` process with an explicit `RUNTIME_DIR`. The Playwright
configs also set the backend `reuseExistingServer: false`, so a suite always owns its backend
process — a restart/cleanup claim is only valid when a fresh process actually starts. Results are
recorded in [`docs/LOCAL_ACCEPTANCE_REPORT.md`](./docs/LOCAL_ACCEPTANCE_REPORT.md).

The three photographs in `data/local_acceptance_inputs/` (healthy-looking, multiple-leaf and
non-rice wheat) are local-only fixtures: they are gitignored and must be present on disk for the
full acceptance matrix. The approved raw dataset under `data/raw/` is likewise required and
never committed.

The backend URL comes from `VITE_API_BASE_URL` (copy `frontend/.env.example` to `frontend/.env`).
If `localhost` resolves to IPv6 while the backend binds IPv4, use `http://127.0.0.1:8000`.

## Demo images

[`demo_images/`](./demo_images/) contains four curated files for UI demonstration only:
three development-split dataset images (Bacterial Leaf Blight, Brown Spot, Leaf Smut) and
one synthetic blank frame that must be rejected with `NO_CLEAR_LEAF_FOUND`. See
[`demo_images/README.md`](./demo_images/README.md) for each file's source, expected
behaviour and the warning that a training/development image is **not** evidence of
generalization. No smartphone images are included or claimed.

## Environment

Copy `.env.example` to `.env` in the repository root for backend settings.
The frontend reads its own `frontend/.env` (see `frontend/.env.example`).

## Data

The approved 120-image dataset is placed at `data/raw/rice_leaf_diseases/` and is **not**
committed. See [`data/README.md`](./data/README.md) for provenance, verified characteristics
and split rules, and [`docs/DATASET_AUDIT.md`](./docs/DATASET_AUDIT.md) for the full audit.

Regenerate the audit and frozen splits:

```powershell
python scripts/audit_dataset.py
python scripts/find_near_duplicates.py
python scripts/build_duplicate_groups.py
python scripts/make_splits.py
python -m pytest tests -q
```

Run the Phase 2 segmentation audit (writes git-ignored panels + the committed
`docs/segmentation_audit/` evidence set):

```powershell
python scripts/run_segmentation_audit.py
```

Segmentation results and the calibration record are in
[`docs/SEGMENTATION_NOTES.md`](./docs/SEGMENTATION_NOTES.md).

**Split protocol v1:** seed 42, 24-image held-out test set (8 per class, singleton images
only), 96-image stratified group-aware 5-fold cross-validation. Verified to reproduce
byte-identically.

## Documentation map

| File | Purpose |
|---|---|
| `PRD.txt` / `docs/PRD.md` | Approved product requirements |
| `PHASE_PLAN.txt` | Detailed phase plan, risks, acceptance criteria |
| `PROJECT_STATUS.md` | What works, what does not, next exact task |
| `docs/DECISIONS.md` | Locked decisions + rationale |
| `docs/ARCHITECTURE.md` | System diagram and component boundaries |
| `docs/FRONTEND.md` | Phase 5 dashboard contract, state matrix, honesty rules and tests |
| `docs/AGENT_HANDOFF.md` | Procedure for the next AI-agent session |
| `docs/QA_REPORT.md` | Phase 6 real-browser E2E results, contract checks, known limitations |
| `docs/LOCAL_ACCEPTANCE_REPORT.md` | 2026-11-09 localhost acceptance matrix, restart-cleanup evidence, timings and limitations |
| `docs/local_acceptance/api_evidence.json` | Machine-readable evidence from the 38-check local acceptance run |
| `docs/DATASET_AUDIT.md` | Phase 1 audit, duplicate review and split protocol |
| `docs/SEGMENTATION_NOTES.md` | Phase 2 segmentation audit, `seg-v1`→`seg-v2` calibration, limitations |
| `docs/segmentation_audit/` | Curated 12-panel visual evidence + audit summary |
| `data/README.md` | Dataset provenance and rules |

## Scope limits (Version 1)

No healthy-leaf classification, no other diseases, no plant-level diagnosis, no multi-leaf
reports, no treatment advice, no accounts, no permanent image storage, no mobile app, and no
MobileNetV2 in the production pipeline.

## Disclaimer

DhanyaDrishti is an academic prototype trained on 120 diseased rice-leaf images. Its severity
output is an experimental visible-lesion-area estimate. It is not a replacement for
agricultural experts, field inspection or plant-pathology diagnosis.
