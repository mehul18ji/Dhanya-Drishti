<p align="center">
  <img src="frontend/public/favicon.svg" width="76" height="76" alt="DhanyaDrishti logo" />
</p>

<h1 align="center">DhanyaDrishti</h1>

<p align="center">
  <strong>Rice-leaf disease analysis, explained stage by stage.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" alt="React 18" /></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" alt="TypeScript 5" /></a>
  <a href="https://scikit-learn.org/"><img src="https://img.shields.io/badge/scikit--learn-classical%20ML-F7931E?logo=scikitlearn&logoColor=white" alt="scikit-learn" /></a>
  <a href="https://opencv.org/"><img src="https://img.shields.io/badge/OpenCV-computer%20vision-5C3EE8?logo=opencv&logoColor=white" alt="OpenCV" /></a>
  <a href="https://vite.dev/"><img src="https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white" alt="Vite 6" /></a>
</p>

DhanyaDrishti turns a single rice-leaf photograph into an inspectable diagnostic report: a
supported disease label, per-class decision-function margins, a segmented lesion-area
estimate, an experimental severity band, and the quality warnings behind the result. The
pipeline is classical computer vision and machine learning — no deep learning and no hidden
probability scores.

**Scope.** The model supports three classes: Bacterial Leaf Blight, Brown Spot and Leaf Smut.
It has no healthy-leaf class and is not intended for treatment decisions. See
[Responsible use](#responsible-use).

## Live Demo

> **Dashboard:** _Public link coming soon._

The frontend is a static Vite application; the API and interactive documentation run as a
separate FastAPI service. Deployment configuration and environment requirements are covered
in [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Capabilities

- **Transparent inference** — per-class SVM decision-function values, the best-vs-second
  margin and the full class ranking. Scores are never presented as probabilities or
  confidence percentages.
- **Reliability first** — unusable images are rejected with a reason, unreliable lesion
  measurements are withheld, and uncertain results carry explicit quality warnings.
- **Visual evidence** — the oriented upload, leaf mask and lesion mask are available as
  in-app full-screen previews. Files download only when the user explicitly asks.
- **Mobile-ready workspace** — responsive layouts, tap-to-upload, mobile history cards,
  accessible dialogs and a light/dark theme.
- **Deployment-aware client** — environment-driven API configuration, automatic recovery
  from sleeping backends, offline detection and an app-wide error boundary.
- **Temporary by design** — predictions and PNG artifacts live in runtime storage and
  disappear on restart, expiry or explicit clear.

## Pipeline

```text
Upload
  → validation (type, size, decode, EXIF orientation)
  → preprocessing (aspect-preserving resize, letterbox, denoise)
  → quality assessment
  → leaf segmentation (HSV + Lab, K-Means, morphology)
  → lesion segmentation inside the leaf mask
  → 50-feature extraction (colour, GLCM texture, shape, lesion, spatial)
  → RBF SVM inference (decision-function margins)
  → experimental severity estimate
  → temporary history and artifact storage
```

| Stage | What happens |
|---|---|
| Validation | File type, size, image decode, dimension limits and EXIF orientation are checked before analysis. |
| Preprocessing | The image is resized without stretching, letterboxed to a square canvas and denoised. |
| Segmentation | A primary leaf mask is produced, followed by a lesion mask constrained to that leaf. |
| Features | A versioned 50-feature schema captures colour, texture, shape, lesion and spatial measurements. |
| Inference | The production bundle verifies its schema and config hashes, then predicts with an RBF SVM. |
| Reporting | The API returns margins, lesion reliability, warnings, provenance, timings and artifact URLs. |

The backend never retrains, recalibrates or reads held-out evaluation rows during a request.

## Model

| Item | Value |
|---|---|
| Dataset | 120 diseased rice-leaf images, 3 classes |
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

## Technology

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 6, TypeScript, Tailwind CSS 3 |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Computer vision | OpenCV, Pillow, scikit-image, NumPy |
| Machine learning | scikit-learn (RBF SVM), joblib |
| Runtime storage | SQLite + local PNG artifacts, temporary only |
| Testing | pytest, Vitest, Testing Library, Playwright |

## Repository Layout

```text
DhanyaDrishti/
├── backend/                 FastAPI service, vision/ML pipeline, configs, tests and bundle
├── frontend/                React + Vite dashboard and Vercel configuration
├── data/                    Dataset guidance, frozen splits and reproducibility snapshots
├── demo_images/             Curated images for interface demonstrations
├── docs/                    Architecture, API contract, decisions, QA and dataset audit
├── notebooks/               Dataset audit, segmentation and model-comparison analysis
├── scripts/                 Audit, split, train, evaluate, export and acceptance tooling
├── tests/end_to_end/        Cross-stack Playwright browser tests
├── DEPLOYMENT.md            Vercel + Render deployment runbook
└── render.yaml              Render blueprint for the API service
```

## Getting Started

**Prerequisites:** Python 3.11+, Node.js 20+ and npm.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

- API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "svm-v1.0.0",
  "runtime_storage": "temporary"
}
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` to the API origin (default local value:
`http://localhost:8000`). If `localhost` resolves to IPv6 while the backend binds IPv4, use
`http://127.0.0.1:8000`.

- Dashboard: <http://localhost:5173>
- Production build: `npm run build`
- Local production preview: `npm run preview`
- Type check: `npm run typecheck`

### API

FastAPI exposes health, model information, prediction, history and artifact endpoints under
`/api/v1`. Request and response contracts are documented in [`docs/API.md`](./docs/API.md).

## Deployment

The repository ships with deployment configuration for a split frontend/API setup:

- **Vercel** — root directory `frontend`; [`frontend/vercel.json`](./frontend/vercel.json)
  handles SPA routing; set `VITE_API_BASE_URL` to the public API origin.
- **Render** — use [`render.yaml`](./render.yaml) or the equivalent manual service; set
  `CORS_ORIGINS` to the exact Vercel origin.
- **Runbook** — environment variables, smoke tests, cold-start behaviour and troubleshooting
  are in [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Verification

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && python -m pytest -q` | 222 passed |
| Split invariants | `python -m pytest tests -q` | 6 passed |
| Frontend unit | `cd frontend && npm test` | 73 passed |
| Type check | `cd frontend && npm run typecheck` | clean |
| Production build | `cd frontend && npm run build` | clean |
| Browser — development | `cd tests/end_to_end && npx playwright test` | 34 passed (Chrome + Edge) |
| Browser — production preview | `npx playwright test --config=playwright.preview.config.ts` | 17 passed (Chrome) |

The browser suites cover the live upload-to-result flow, artifact preview and download,
history, phone layouts, backend cold-start recovery and offline/error states.

## Responsible Use

- **Three classes only.** There is no healthy-leaf or out-of-distribution class.
  Healthy-looking or non-rice inputs may be `uncertain` or rejected, never “healthy”.
- **Margins, not probabilities.** Decision-function scores are not calibrated confidence
  values and must not be presented as such.
- **Experimental severity.** The severity band is a visible-lesion-area estimate under
  provisional thresholds, not a validated agronomic grade.
- **Limited evidence base.** The model was trained on 120 images and evaluated on 24; it has
  not been validated on smartphone or field-camera photographs.
- **Not professional advice.** DhanyaDrishti is a research and educational system, not a
  substitute for expert plant-pathology diagnosis, field inspection or treatment advice.

## Documentation

| Document | Purpose |
|---|---|
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | Vercel + Render release, environment and failure handling |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | System boundaries and component flow |
| [`docs/API.md`](./docs/API.md) | Endpoint contracts and response rules |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | Engineering decisions and rationale |
| [`docs/QA_REPORT.md`](./docs/QA_REPORT.md) | Browser, contract and integration test evidence |
| [`docs/DATASET_AUDIT.md`](./docs/DATASET_AUDIT.md) | Dataset audit, duplicate review and split protocol |
