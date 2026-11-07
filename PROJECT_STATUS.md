# PROJECT STATUS

> Required by PRD §24. Update at the end of every working session.
> Format is fixed — keep the labels exactly as written.
> Phase 2 milestone definitions live in `PHASE_PLAN.txt` §5 (Phase 2 → "Phase 2 milestones");
> this file only names the active one.

Current phase: Phase 2 — Classical CV pipeline (COMPLETE — all seven milestones M1–M7 met)
Last completed task: Phase 2 M6/M7 — split-aware 120-image segmentation audit (`scripts/run_segmentation_audit.py`), `seg-v2` calibration (`lab.min_chroma` 10→20, lesion healthy-reference guard, `border_exclusion_px` 2→6), curated evidence set in `docs/segmentation_audit/`, `docs/SEGMENTATION_NOTES.md`, `notebooks/02_segmentation_experiments.ipynb`.
Tests last run: 2026-11-07 — `python -m pytest` in `backend/` (70 passed) and `python -m pytest tests -q` at the root (split-manifest invariants, 6 passed).
Test result: 76 tests passing, 0 failing (70 backend vision/API/config + 6 split invariants).
Current branch: main
Latest commit: d5d1154 (all Phase 2 work is intentionally uncommitted — commits are paused at the user's request)
What works:
- Phase 1 data pipeline: audit manifest, near-duplicate review (13 groups / 27 images), frozen split protocol v1 (24-image singleton test + group-aware 5-fold CV), split invariant tests, audit notebook.
- Phase 2 M1: versioned YAML configs (`seg-v2`, `quality-v1`), strict validation, content hashing; `seg-v1` archived and still loadable.
- Phase 2 M2: EXIF-aware decode, no-stretch working image, margin crop, letterbox canvas, reversible `CanvasTransform`, denoise; quality metrics with separate warnings/rejections and leaf-mask-only exposure.
- Phase 2 M3: HSV+Lab leaf candidates, seeded K-Means merge, morphology, candidate scoring, ≥0.65 full-frame fallback, multi-leaf warning, `NO_CLEAR_LEAF_FOUND`.
- Phase 2 M4: leaf-relative lesion segmentation (hue/a*/b*/value shifts + K-Means), border exclusion, leaf-mask intersection, plausibility warning, and an explicit unreliable state when no healthy-green reference exists.
- Phase 2 M5: `vision/pipeline.py` (one stage composition + timings) and `vision/diagnostics.py` (4-up review panels).
- Phase 2 M6: 120/120 plausible leaf masks on the dataset (dev 96/96, held-out test 24/24), 0 rejected, 33 uncertain, 8 documented full-frame fallbacks, mean pipeline time 130.6 ms (p95 138.3 ms).
- Phase 2 M7: `docs/SEGMENTATION_NOTES.md` with the calibration before/after, committed curated panels + summary, notebook 02.
What does not work:
- No feature extraction, no SVM/RF/KNN training, no prediction API, no upload/history UI (Phases 3–5 onwards).
- No segmentation ground-truth annotation exists, so "plausible mask" is a visual review, not an IoU score.
- A faint lesion band can remain on the dark lower edge of some Bacterial leaf blight strips; documented limitation, not fixed.
- Thresholds are calibrated on white-paper studio photos; phone photos with cluttered backgrounds are untested.
Next exact task: Phase 3 M1 — write `backend/app/vision/feature_extraction.py` (versioned colour/GLCM/shape/lesion/spatial schema v1.0.0) that consumes `vision/pipeline.py::run_segmentation` outputs, plus a feature-name/order contract test.
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
