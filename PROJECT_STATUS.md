# PROJECT STATUS

> Required by PRD §24. Update at the end of every working session.
> Format is fixed — keep the labels exactly as written.
> Phase 2 milestone definitions live in `PHASE_PLAN.txt` §5 (Phase 2 → "Phase 2 milestones");
> this file only names the active one.

Current phase: Phase 2 — Classical CV pipeline (COMPLETE — all seven milestones M1–M7 met) → Phase 3 next, after verification below.
Last completed task: Phase 2 M6/M7 — seg-v2 evidence set regenerated from the frozen audit inputs under the active `seg-v2` config: `scripts/run_segmentation_audit.py`, 12 curated panels in `docs/segmentation_audit/`, committed `curated_manifest.json` + `audit_summary.json` and `docs/SEGMENTATION_NOTES.md`. The archived baseline (`seg-v1`) remains separate at `backend/configs/archive/segmentation.seg-v1.yaml` and `data/processed/segmentation_audit/baseline-seg-v1/`. Phase 2 closed with the `LESION_REFERENCE_UNAVAILABLE` unreliable-state guard added to the lesion pipeline.
Tests last run: 2026-11-07 — `python -m pytest backend/tests` (70 passed) and `python -m pytest tests -q` (split-manifest invariants, 6 passed).
Test result: 76 tests passing, 0 failing (70 backend vision/api/config + 6 split invariants).
Final seg-v2 audit summary: 120 images (development 96 / held-out test 24); plausible leaf mask 120/120 (dev 96/96, test 24/24); clean 87, uncertain 33, rejected 0; full-frame fallback 8, multiple leaves 0, lesion unreliable 0; per class BLB 37/3/0, brown_spot 23/17/0, leaf_smut 27/13/0; mean pipeline time 189.13 ms, p50 171.61 ms, p95 227.43 ms, max 1631.91 ms; lesion area mean 13.707 % / p50 10.446 % / p95 39.903 %; warning histogram SMALL_IMAGE 19, BLURRY_IMAGE 10, FULL_FRAME_FALLBACK 8, BRIGHT_IMAGE 3, LOW_CONTRAST 1. Development and held-out test blocks are reported separately and were not used for calibration.
Phase 2 evidence verification: completed 2026-11-07 — the 12 committed panels in `docs/segmentation_audit/` were compared byte-for-byte with the pipeline-produced panels in `data/processed/segmentation_audit/seg-v2/panels/`. All 12 SHA-256 hashes match: Bacterial_leaf_blight__DSC_0365.png, Bacterial_leaf_blight__DSC_0703.png, Brown_spot__DSC_0121.png, Brown_spot__DSC_0105.png, Brown_spot__DSC_0114.png, Brown_spot__DSC_0109.png, Leaf_smut__DSC_0504.png, Leaf_smut__DSC_0501.png, Leaf_smut__DSC_0502.png, Leaf_smut__DSC_0511.png, Leaf_smut__DSC_0508.png, Leaf_smut__DSC_0515.png. Committed evidence set is exactly what the active `seg-v2` pipeline produced. No panels, manifest or summary were changed by this verification.
Current branch: main
Latest commit: d5d1154 (all Phase 2 work is intentionally uncommitted — commits are paused at the user's request)
What works:
- Phase 1 data pipeline: audit manifest, near-duplicate review (13 groups / 27 images), frozen split protocol v1 (24-image singleton test + group-aware 5-fold CV), split invariant tests, audit notebook.
- Phase 2 M1: versioned YAML configs (`seg-v2`, `quality-v1`), strict validation, content hashing; `seg-v1` archived and still loadable.
- Phase 2 M2: EXIF-aware decode, no-stretch working image, margin crop, letterbox canvas, reversible `CanvasTransform`, denoise; quality metrics with separate warnings/rejections and leaf-mask-only exposure.
- Phase 2 M3: HSV+Lab leaf candidates, seeded K-Means merge, morphology, candidate scoring, ≥0.65 full-frame fallback, multi-leaf warning, `NO_CLEAR_LEAF_FOUND`.
- Phase 2 M4: leaf-relative lesion segmentation (hue/a*/b*/value shifts + K-Means), border exclusion, leaf-mask intersection, plausibility warning, and an explicit unreliable state when no healthy-green reference exists.
- Phase 2 M5: `vision/pipeline.py` (one stage composition + timings) and `vision/diagnostics.py` (4-up review panels).
- Phase 2 M6: 120/120 plausible leaf masks on the dataset (dev 96/96, held-out test 24/24), 0 rejected, 33 uncertain, 8 documented full-frame fallbacks, mean pipeline time 162.12 ms (p95 178.98 ms).
- Phase 2 M7: `docs/SEGMENTATION_NOTES.md` with the calibration before/after, committed curated seg-v2 panels + summary, notebook 02.
What does not work:
- No feature extraction, no SVM/RF/KNN training, no prediction API, no upload/history UI (Phases 3–5 onwards).
- No segmentation ground-truth annotation exists, so "plausible mask" is a visual review, not an IoU score.
- A faint lesion band can remain on the dark lower edge of some Bacterial leaf blight strips; documented limitation, not fixed.
- Thresholds are calibrated on white-paper studio photos; phone photos with cluttered backgrounds are untested.
Next exact task: Phase 3 M1 — write `backend/app/vision/feature_extraction.py` (versioned colour/GLCM/shape/lesion/spatial schema v1.0.0) that consumes `vision/pipeline.py::run_segmentation` outputs, plus a feature-name/order contract test. Before training or feature-matrix building, treat lesion unreliability as first-class: any `uncertain` lesion result (including `LESION_REFERENCE_UNAVAILABLE`) must never become `0% lesion` or be read as "healthy". Preserve `lesion_reliable`, `warnings`, and the segmentation status into the feature matrix and later severity reporting.

Phase 3 input contract (for all 120 known-disease images): the 120 images remain available for disease-classification work, but an `uncertain` lesion result must never silently become `0% lesion` or "healthy". Lesion reliability/uncertainty must be preserved explicitly for later feature handling and severity reporting.

Phase 3 environment/decision reminder: the required classical ML pipeline runs locally on CPU through versioned Python scripts. Google Colab is out of scope for the required workflow; local Jupyter notebooks are optional exploration tools only.
Known blockers: None.
Decisions that must not be changed:
- Only the 120-image, 3-class dataset; no healthy class; no images excluded.
- Split protocol v1 (seed 42, 24-image singleton test, 96-image group-aware 5-fold CV) is frozen; changing it invalidates metrics. Calibration never uses the 24 held-out test images.
- Confirmed duplicate groups never cross train/validation/test boundaries.
- Classical workflow only; SVM/RF/KNN compared; winner chosen by macro F1.
- React + Vite + Tailwind + TypeScript frontend; Python 3.11 + FastAPI backend; OpenCV + scikit-learn.
- SQLite/temp files only, wiped at startup; no permanent image storage.
- CPU-only; no TensorFlow/CUDA/MobileNetV2 in Version 1.
- Severity is an experimental lesion-area estimate with its disclaimer.
- No image is ever stretched: uniform scale + letterbox only (PRD §8).
