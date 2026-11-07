# DhanyaDrishti — Decisions Log

> Locked decisions and their rationale. The PRD is the top authority; this file records
> *how* the team chose to implement it and *why*, so later sessions do not re-litigate
> settled questions. Update it when a decision genuinely changes, with a dated note.

---

## 1. Locked product decisions (from PRD §2 — do not change)

| ID | Decision |
|---|---|
| D-01 | Only the approved 120-image Kaggle Rice Leaf Diseases dataset is used. |
| D-02 | Exactly three labels: Bacterial Leaf Blight, Brown Spot, Leaf Smut. |
| D-03 | The professor's classical workflow is mandatory: preprocessing → aspect-safe resize → denoise → HSV/Lab → leaf segmentation → disease segmentation → colour/texture/shape/lesion features → SVM/RF/KNN comparison → prediction → Mild/Moderate/Severe estimate. |
| D-04 | Frontend: React + Vite + Tailwind CSS + TypeScript. |
| D-05 | Backend: Python 3.11 + FastAPI + Uvicorn. |
| D-06 | OpenCV for image processing; scikit-learn for SVM/RF/KNN; scikit-image for GLCM. |
| D-07 | SQLite is temporary runtime storage only. No permanent image storage. |
| D-08 | CPU-only for Version 1. No CUDA, TensorFlow or MobileNetV2 dependency. |
| D-09 | MobileNetV2 is a future optional experiment and must never replace the classical pipeline. |
| D-10 | No healthy-leaf class, no treatment advice, no accounts, no mobile app. |
| D-11 | Severity is an experimental lesion-area estimate, displayed with its disclaimer. |
| D-12 | Model selection is by macro F1-score from evaluation, never pre-assumed. |

## 2. Engineering decisions made during Phase 0

| ID | Decision | Rationale |
|---|---|---|
| E-01 | Plan lives in `PHASE_PLAN.txt` at the repository root. | Persistent, tool-agnostic, visible to any agent; `PRD.txt` stays untouched as the authority. |
| E-02 | `docs/PRD.md` is a copy of `PRD.txt`. | PRD §24 requires `docs/PRD.md` as the session entry point while `PRD.txt` remains the source artifact. |
| E-03 | Raw dataset moved to `data/raw/rice_leaf_diseases/` and git-ignored. | Matches PRD §17/§18 and keeps raw images out of version control. Originals are byte-identical. |
| E-04 | `opencv-python-headless` is the pinned OpenCV package. | Identical API, smaller footprint, and it is deployable on Render without GUI libraries. |
| E-05 | Backend settings are typed via `pydantic-settings`, read from the root `.env`. | One configuration path for local and deployed runs; no scattered `os.getenv`. |
| E-06 | `CORS_ORIGINS` is a comma-separated string with a parsed list property. | Avoids pydantic-settings JSON parsing failures on simple `.env` values. |
| E-07 | Health endpoint reports `model_loaded: false` and `model_version: null` before Phase 4. | The API must never advertise a model it does not have. |
| E-08 | Prediction and other business errors use `AppError` subclasses with stable `reason_code`s. | Frontend can branch on codes instead of parsing prose (PRD §15). |
| E-09 | Tailwind CSS v3 with `tailwind.config.ts` (not v4 CSS-first config). | Matches the PRD's stated file and has the widest tooling stability. |
| E-10 | No model or vision package is imported by the Phase 0 app. | Keeps startup light and honest; ML wiring belongs to Phase 3-4. |
| E-11 | Design tokens (`ink`, `accent`, `warn`) live in Tailwind theme, not ad-hoc hex values. | Enforces the PRD §6 visual direction consistently across pages. |
| E-12 | `backend/.runtime/` is git-ignored and wiped at startup. | PRD §16 temporary-storage contract. |

## 3. Planned decisions to confirm during later phases

These are *provisional*; each is settled by evidence, not preference, and must be recorded here
when decided.

| ID | Open question | Planned resolution |
|---|---|---|
| P-01 | Full-frame leaf fallback threshold (start 0.65 green ratio) | Calibrate on the 13 close-up images in Phase 2 |
| P-02 | Hard/soft image-size thresholds (start 64 px / 224 px) | Justify against the 9 small dataset images in Phase 2 |
| P-03 | Near-duplicate detection method | dHash-16 + HSV histogram + SSIM, manual adjudication in Phase 1 |
| P-04 | Feature budget (target ~40–80 features) | Prune by variance/correlation in Phase 3; freeze schema v1 |
| P-05 | Uncertainty probability threshold | Tune on out-of-fold CV probabilities in Phase 3 |
| P-06 | Selected classifier | Whichever wins by macro F1 in Phase 3 |
| P-07 | Canvas size (start 512 px long side) | Balance CPU latency vs lesion visibility in Phase 2 |
| P-08 | History expiry default (start 60 min) | Confirm with mentor; keep configurable |

## 4. Change procedure

1. Propose the change with evidence (test result, measurement, mentor instruction).
2. If it touches a D-xx decision, it requires mentor approval and a PRD update first.
3. Otherwise, add a dated row here and update `PHASE_PLAN.txt` / `PROJECT_STATUS.md` if affected.
