# DhanyaDrishti

Academic prototype dashboard for **rice-leaf disease analysis** using a fully **classical**
computer-vision and machine-learning pipeline (no deep learning in Version 1).

Upload one photograph of a diseased rice leaf and receive:

- a predicted disease label — **Bacterial Leaf Blight**, **Brown Spot** or **Leaf Smut**;
- a confidence score;
- a lesion-area estimate;
- an *experimental* severity estimate (Mild / Moderate / Severe);
- quality and uncertainty warnings when the result is unreliable;
- temporary prediction history for the current backend session.

> ⚠ This prototype supports only three diseased rice-leaf categories. Do not upload healthy
> leaves. Results are academic estimates and must not be used as professional agricultural advice.

---

## Status

**Current phase: Phase 4 — FastAPI inference service (in progress). Phase 3 is complete; Phase 4 milestones M1–M4 are complete.**

| Area | State |
|---|---|
| Repository foundation, docs, env templates | Done |
| Frontend dashboard shell (routing, layout, pages) | Done |
| Backend health API + typed config | Done |
| Dataset audit and reproducible splits | Done (Phase 1) |
| Classical CV pipeline (preprocessing, quality, leaf + lesion segmentation, audit) | Done (Phase 2) |
| Features + SVM/RF/KNN comparison, production model bundle | Done (Phase 3) |
| Inference service, lifespan load, `/health`, `/model-info`, upload validation, preprocessing orchestration | Done (Phase 4 M1–M4) |
| `POST /predict`, severity, temporary history, artifact serving | Not started (Phase 4 M5+) |
| Upload / result / history UI | Not started (Phase 5) |
| QA, model card, deployment | Not started (Phases 6-7) |

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

Expected health response in Phase 0:

```json
{
  "status": "ok",
  "model_loaded": false,
  "model_version": null,
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

The backend URL comes from `VITE_API_BASE_URL` (copy `frontend/.env.example` to `frontend/.env`).

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
| `docs/AGENT_HANDOFF.md` | Procedure for the next AI-agent session |
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
