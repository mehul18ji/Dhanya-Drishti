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

- Environment and tooling: the required classical ML pipeline runs locally on CPU through versioned Python scripts. Google Colab is out of scope for the required workflow; local Jupyter notebooks are optional exploration tools only.

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
| E-13 | Class folder names are mapped to stable slugs: `Bacterial leaf blight → bacterial_leaf_blight`, `Brown spot → brown_spot`, `Leaf smut → leaf_smut`. | Folder names contain spaces and inconsistent capitalisation; slugs are safe in JSON, CSV and feature reports. |
| E-14 | `dataset_version` is `ds-<sha256[:12]>` over sorted `md5 + path` pairs. | Ties every metric and artifact to the exact bytes analysed; any re-download changes the version. Current: `ds-cc74ed659044`. |
| E-15 | Near-duplicate screening uses dHash-16 + HSV histogram + SSIM + ORB/RANSAC over **all** 7,140 pairs, then manual visual adjudication. | Coarse average-hash produced 298 false positives; ORB is required because several same-leaf pairs are differently framed and have low SSIM. |
| E-16 | 13 confirmed duplicate groups (27 images) are **retained**, not deleted; splits are group-aware. | Deleting images would break the approved 120-image dataset; grouping prevents leakage while preserving all data. |
| E-17 | Split protocol v1: seed 42; held-out test = 24 images (8/class) from **singleton images only**; remaining 96 = stratified 5-fold `StratifiedGroupKFold`. | Test metrics are not inflated by near-identical twins; no duplicate group is split across train/validation/test. |
| E-18 | EXIF orientation is applied before any analysis (10 dataset images carry orientation 3). | Without it those leaves are analysed upside-down; PRD §8 requires EXIF correction. |
| E-19 | Image-quality checks (over-exposure, brightness) are computed **inside the leaf mask**, not the whole frame. | White paper backgrounds dominate global exposure statistics (p95 = 64% "over-exposed" pixels), which would create false warnings. |

## 3. Decisions resolved in Phase 1

| ID | Decision | Evidence |
|---|---|---|
| P-01 | Full-frame leaf fallback threshold starts at **0.65** leaf-green fraction. | 15 images exceed 0.65; 11 exceed 0.70. Calibrate and freeze in Phase 2. |
| P-02 | Size gate: hard reject **< 64 px** short side, soft warning **< 224 px**. | 9 images are below 128 px (smallest 301×71); a 256 px gate would reject 25 images. |
| P-03 | Near-duplicate method: dHash-16 + HSV histogram + SSIM + ORB/RANSAC + visual adjudication. | 17 candidates → 15 confirmed pair relationships in 13 groups, 2 rejected. 0 cross-class duplicates. |

## 4. Decisions resolved in Phase 2

| ID | Decision | Evidence |
|---|---|---|
| P-07 | Frozen the processing geometry: 768 px aspect-preserving working image, 512 px letterboxed canvas, 8 % crop margin. | 120-image audit: mean 130.6 ms/image on CPU (p95 138.3 ms); lesions remain visible at 512 px. `segmentation.yaml` `preprocessing`. |
| P-09 | `seg-v2` replaces `seg-v1` after the visual audit, with three corrections: `leaf.lab.min_chroma` 10→20 (warm paper shadow was merged into the leaf mask on 40 BLB images and then reported as lesion), a lesion healthy-reference guard (`lesion.min_healthy_reference_fraction = 0.01`, result marked `reliable=False`), and `lesion.border_exclusion_px` 2→6 (leaf-edge shading counted as lesion along the whole outline). | Before/after numbers and panels: `docs/SEGMENTATION_NOTES.md` §4. `seg-v1` preserved at `backend/configs/archive/segmentation.seg-v1.yaml`. |
| P-10 | Calibration is split-aware: only the 96 development images may justify a threshold change; the 24 held-out test images are reported separately and never inspected for tuning. | `scripts/run_segmentation_audit.py` writes `development` and `held_out_test` blocks separately; no seg-v2 change references a test image. |
| P-11 | A lesion estimate that cannot be calibrated is reported as unreliable, never as a confident number. | A fully brown leaf used to return "0 % lesions" because it was its own colour reference; `LESION_REFERENCE_UNAVAILABLE` + `reliable=False` now force the Phase 4 `uncertain` path. (`tests/test_lesion_segmentation.py`) |
| P-12 | Visual evidence policy: the full 120-image render set stays in git-ignored `data/processed/segmentation_audit/`, while a fixed, reproducible 12-panel curated set is committed under `docs/segmentation_audit/`. | Keeps the repository light while giving the mentor inspectable proof; `curated_manifest.json` records source path and reason per panel. |

## 4b. Decisions resolved in Phase 3

| ID | Decision | Evidence |
|---|---|---|
| P-13 | **Locked missing-value rule.** Raw feature matrices preserve `NaN` values for unreliable lesion/spatial features. During later classifier training, missing-value imputation and missingness indicators must be fitted only on each training fold inside the scikit-learn pipeline. Uncertain lesion values must never be replaced with `0.0`, and images must not be silently dropped. | `backend/app/vision/feature_extraction.py` writes `NaN` + `missing_features` for an uncalibrated lesion; `backend/tests/test_feature_extraction.py` pins "uncertain is missing, not 0.0" against "a measured 0 % stays 0 %". Related: P-11. |

## 5. Open questions for later phases

| ID | Open question | Planned resolution |
|---|---|---|
| P-04 | Feature budget (target ~40–80 features) | Prune by variance/correlation in Phase 3; freeze schema v1 |
| P-05 | Uncertainty probability threshold | Tune on out-of-fold CV probabilities in Phase 3 |
| P-06 | Selected classifier | Whichever wins by macro F1 in Phase 3 |
| P-08 | History expiry default (start 60 min) | Confirm with mentor; keep configurable |

## 6. Change procedure

1. Propose the change with evidence (test result, measurement, mentor instruction).
2. If it touches a D-xx decision, it requires mentor approval and a PRD update first.
3. Otherwise, add a dated row here and update `PHASE_PLAN.txt` / `PROJECT_STATUS.md` if affected.
