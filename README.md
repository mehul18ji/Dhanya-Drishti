# DhanyaDrishti

**Rice-leaf disease analysis with a classical computer-vision and machine-learning pipeline.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-classical%20ML-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![Status](https://img.shields.io/badge/status-Phase%206%20complete-2ea44f)](#project-status)

DhanyaDrishti is an academic web dashboard that examines a single photograph of a diseased
rice leaf and returns a supported disease label, decision-margin scores, a lesion-area
estimate, and an experimental severity estimate. The complete pipeline is **classical
computer vision and machine learning** — there is no deep learning in Version 1.

> **Scope:** three diseased rice-leaf classes only — Bacterial Leaf Blight, Brown Spot and
> Leaf Smut. The system does not detect healthy leaves, other diseases, or plant-level
> conditions. Results are academic estimates, not agricultural advice.

---

## Live Demo

Phase 7 cloud deployment has not started yet. The public frontend URL will be added here
after the Vercel deployment is complete.

| Component | URL | Status |
|---|---|---|
| Frontend (Vercel) | _Placeholder — to be added after deployment_ | Pending |
| Backend API | `http://localhost:8000` | Local development |

<!-- VERCEL_FRONTEND_URL: replace the placeholder row above after Phase 7 deployment. -->

---

## Overview

The project covers the full path from an uploaded leaf photograph to an honest,
inspectable result:

- **Disease prediction** — one of three supported classes.
- **Decision-margin scores** — per-class SVM decision-function values and a best-vs-second
  margin. These are **not** calibrated probabilities or confidence percentages.
- **Lesion analysis** — estimated visible-lesion area with explicit reliability gating.
- **Experimental severity** — Mild / Moderate / Severe from lesion-area thresholds, always
  shown with its disclaimer.
- **Quality and uncertainty warnings** — the UI reports when a result is unreliable instead
  of presenting a false confirmation.
- **Temporary history** — predictions and PNG artifacts last only for the current backend
  session and are wiped on restart.

The application is intentionally conservative: rejected inputs return no disease label, no
severity and no history entry.

---

## How It Works

```text
Upload
  → upload validation (type, size, decode, EXIF)
  → preprocessing (aspect-preserving resize, letterbox, denoise)
  → quality assessment
  → leaf segmentation (HSV + Lab, K-Means, morphology)
  → lesion segmentation inside the leaf mask
  → 50-feature extraction (colour, GLCM texture, shape, lesion, spatial)
  → SVM inference (decision-function margins, not probabilities)
  → experimental severity estimate
  → temporary history and artifact storage
```

| Stage | What happens |
|---|---|
| Validation | File type, size, image decode, dimension limits and EXIF orientation are checked before analysis. |
| Preprocessing | The image is resized without stretching, letterboxed to a square canvas, and denoised. |
| Segmentation | A primary leaf mask is produced, followed by a lesion mask constrained to that leaf. |
| Feature extraction | A versioned 50-feature schema captures colour, texture, shape, lesion and spatial measurements. |
| Inference | The production bundle verifies its schema and config hashes, then predicts with an RBF SVM. |
| Reporting | The API returns margins, lesion reliability, warnings, provenance, timings and artifact URLs. |

The backend never retrains, recalibrates or reads held-out evaluation rows during a request.

---

## Model and Evaluation

| Item | Value |
|---|---|
| Dataset | 120 approved diseased rice-leaf images, 3 classes |
| Split protocol | 96 development images (group-aware 5-fold CV) / 24 held-out images (8 per class) |
| Candidates compared | RBF SVM, Random Forest, K-Nearest Neighbours |
| Selected model | RBF SVM (`C=1.0`, `gamma="scale"`) |
| Cross-validation macro F1 | **0.8412 ± 0.0604** |
| Held-out macro F1 | **0.7855** (n = 24) |
| Held-out accuracy | **0.7917** |
| Score type | Decision-function margin — not a probability |
| Production bundle | `svm-v1.0.0`, feature set `1.0.0` |

The held-out set was evaluated once after model selection and was not used for tuning. The
24-image sample is small, so the final metric carries sampling uncertainty.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 6, TypeScript, Tailwind CSS 3 |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Computer vision | OpenCV, Pillow, scikit-image, NumPy |
| Machine learning | scikit-learn (RBF SVM), joblib |
| Runtime storage | SQLite + local PNG artifacts, temporary only |
| Testing | pytest, Vitest, Testing Library, Playwright |

---

## Repository Structure

```text
DhanyaDrishti/
├── backend/                 FastAPI app, vision/ML modules, configs, tests, production bundle
├── frontend/                React + Vite + TypeScript dashboard
├── data/                    Raw dataset (ignored), frozen splits, tracked reproducibility snapshots
├── demo_images/             Curated UI-only demo images and provenance notes
├── docs/                    Architecture, API, QA, acceptance evidence and model documentation
├── notebooks/               Dataset audit, segmentation and model-comparison notebooks
├── scripts/                 Audit, split, train, evaluate, export and acceptance scripts
└── tests/end_to_end/        Cross-stack Playwright browser tests
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- Git

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

- API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>

Expected health response with the production bundle loaded:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "svm-v1.0.0",
  "runtime_storage": "temporary"
}
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

- Dashboard: <http://localhost:5173>
- Build: `npm run build`
- Type check: `npm run typecheck`

Set the backend URL through `VITE_API_BASE_URL` (copy `frontend/.env.example` to
`frontend/.env`). If `localhost` resolves to IPv6 while the backend binds IPv4, use
`http://127.0.0.1:8000`.

### Dataset and Local Inputs

The approved 120-image dataset is **not committed**. Place it at
`data/raw/rice_leaf_diseases/` before running the full pipeline, audits or acceptance
matrix. The local acceptance photographs under `data/local_acceptance_inputs/` are also
gitignored and must be present on disk for the 38-check acceptance run.

See [`data/README.md`](./data/README.md) and [`docs/DATASET_AUDIT.md`](./docs/DATASET_AUDIT.md)
for provenance and split rules.

---

## Testing and Quality

Last verified on 2026-11-09:

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && python -m pytest -q` | **222 passed** |
| Root split invariants | `python -m pytest tests -q` | **6 passed** |
| Frontend component/API | `cd frontend && npm test` | **64 passed** |
| Frontend typecheck | `npm run typecheck` | **clean** |
| Frontend build | `npm run build` | **clean** |
| Playwright — development | `cd tests/end_to_end && npx playwright test` | **22 passed** (Chrome + Edge) |
| Playwright — production preview | `npx playwright test --config=playwright.preview.config.ts` | **11 passed** (Chrome) |
| Local acceptance matrix | `python scripts/run_local_acceptance.py` | **38 / 38 checks** |
| Restart cleanup | `python scripts/check_restart_cleanup.py` | **PASS** |

The acceptance matrix uses a real backend process, real dataset images and a real model
bundle. It covers upload validation, orientation handling, quality warnings, rejection
behaviour, history, artifact serving, clear-history and a fresh-process restart with the
same runtime directory.

---

## Demo Images

[`demo_images/`](./demo_images/) contains four curated files for **UI demonstration only**:
three development-split dataset images and one synthetic blank frame that must be rejected
with `NO_CLEAR_LEAF_FOUND`.

See [`demo_images/README.md`](./demo_images/README.md) for each file's source, expected
behaviour and the warning that a training/development image is **not evidence of
generalization**. No smartphone images are included or claimed.

---

## Documentation

| Document | Purpose |
|---|---|
| [`PRD.txt`](./PRD.txt) | Approved product requirements |
| [`PHASE_PLAN.txt`](./PHASE_PLAN.txt) | Phase-wise plan, risks and acceptance criteria |
| [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) | Current state and next exact task |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | System boundaries and component flow |
| [`docs/API.md`](./docs/API.md) | Endpoint contracts and response rules |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | Locked decisions and rationale |
| [`docs/QA_REPORT.md`](./docs/QA_REPORT.md) | Browser E2E, contract checks and known limitations |
| [`docs/LOCAL_ACCEPTANCE_REPORT.md`](./docs/LOCAL_ACCEPTANCE_REPORT.md) | Localhost acceptance evidence and timings |
| [`docs/DATASET_AUDIT.md`](./docs/DATASET_AUDIT.md) | Dataset audit, duplicate review and split protocol |

---

## Project Status

| Phase | State |
|---|---|
| 1 — Dataset audit and reproducible splits | Complete |
| 2 — Classical vision pipeline and segmentation audit | Complete |
| 3 — Features, model comparison and production bundle | Complete |
| 4 — FastAPI service, prediction, history and artifacts | Complete |
| 5 — React dashboard and component tests | Complete |
| 6 — Integration, QA, local acceptance and model card | Complete |
| 7 — Cloud deployment | **Not started** |

The current repository is prepared for Phase 7 deployment preparation. No cloud
deployment has been performed.

---

## Limitations

- **Three classes only.** There is no healthy-leaf class and no out-of-distribution class.
  Healthy-looking or non-rice inputs may return `uncertain` or `rejected`, never “healthy”.
- **Academic prototype.** Results are not a substitute for expert plant-pathology
  diagnosis, field inspection or treatment advice.
- **Small held-out sample.** The final metric is based on 24 images; expect meaningful
  sampling uncertainty.
- **No smartphone or field validation.** Tests use the approved dataset and synthetic
  fixtures. No smartphone result is claimed.
- **Uncalibrated scores.** The SVM exposes decision-function margins, not probabilities.
  The interface does not present confidence percentages.
- **Experimental severity.** Severity is a visible-lesion-area estimate under provisional
  thresholds, not an agronomic grade.
- **Temporary storage only.** History and artifacts are wiped on restart, expiry or
  explicit clear. Nothing is permanently stored.
- **CPU-only, single-machine timings.** Performance figures are local observations, not a
  production SLA.

---

## Disclaimer

DhanyaDrishti is an academic prototype trained on 120 diseased rice-leaf images. Its
severity output is an experimental visible-lesion-area estimate. It is not a replacement
for agricultural experts, field inspection or plant-pathology diagnosis.
