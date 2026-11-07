# PROJECT STATUS

> Required by PRD §24. Update at the end of every working session.
> Format is fixed — keep the labels exactly as written.
> Phase 2 milestone definitions live in `PHASE_PLAN.txt` §5 (Phase 2 → "Phase 2 milestones");
> this file only names the active one.

Current phase: Phase 3 — Features and classical ML comparison (M1 COMPLETE: versioned feature extractor + feature-name/order contract test).
Last completed task (Phase 3 M1): `backend/app/vision/feature_extraction.py` added — the single, versioned feature extractor (`FEATURE_SET_VERSION = "1.0.0"`, 50 features) consuming `vision/pipeline.py::run_segmentation` outputs: colour (per-channel mean/std for RGB/HSV/Lab + 4 quantiles, all normalised to 0–1), GLCM texture (contrast, dissimilarity, homogeneity, energy, correlation on the leaf-only greyscale), shape (area fraction, fill ratio, aspect, perimeter, circularity, solidity, convexity, equivalent-diameter ratio), lesion (area ratio, count per kpx, largest/mean ratio, perimeter ratio, compactness) and spatial (centroid offset, spread, border distance, four quadrant ratios). Machine-readable schema via `feature_schema()`; provenance (seg-v2 / quality-v1 versions + SHA-256) attached through `FeatureExtractionResult.schema()`. Lesion honesty is enforced: when the lesion stage is uncalibrated (`reliable=False` or `LESION_REFERENCE_UNAVAILABLE`) the lesion and spatial features are `NaN` and listed in `missing_features`, `lesion_area_percentage` is `None`, and status is `uncertain` — never `0 %`. A rejected image produces `values=None` rather than a zero-filled vector. Contract tests in `backend/tests/test_feature_extraction.py` (8 tests) assert the schema order/length, determinism, provenance, rejected-image behaviour, missing-not-zero for an unreliable lesion, and a genuine measured `0 %` staying `0`. No model training, no Phase 2 segmentation/threshold/split/evidence change. `scikit-image` (already declared in `backend/requirements.txt`) was installed in the local venv because it was missing at runtime.
Previously completed: Phase 2 M6/M7 — seg-v2 evidence set regenerated from the frozen audit inputs under the active `seg-v2` config: `scripts/run_segmentation_audit.py`, 12 curated panels in `docs/segmentation_audit/`, committed `curated_manifest.json` + `audit_summary.json` and `docs/SEGMENTATION_NOTES.md`. The archived baseline (`seg-v1`) remains separate at `backend/configs/archive/segmentation.seg-v1.yaml` and `data/processed/segmentation_audit/baseline-seg-v1/`. Phase 2 closed with the `LESION_REFERENCE_UNAVAILABLE` unreliable-state guard added to the lesion pipeline.
Tests last run: 2026-11-07 (after Phase 3 M1) — `cd backend && python -m pytest` (78 passed) and `python -m pytest tests` (split-manifest invariants, 6 passed).
Test result: 84 tests passing, 0 failing (78 backend vision/api/config/feature-extraction + 6 split invariants).
Final seg-v2 audit summary: 120 images (development 96 / held-out test 24); plausible leaf mask 120/120 (dev 96/96, test 24/24); clean 87, uncertain 33, rejected 0; full-frame fallback 8, multiple leaves 0, lesion unreliable 0; per class BLB 37/3/0, brown_spot 23/17/0, leaf_smut 27/13/0; mean pipeline time 189.13 ms, p50 171.61 ms, p95 227.43 ms, max 1631.91 ms; lesion area mean 13.707 % / p50 10.446 % / p95 39.903 %; warning histogram SMALL_IMAGE 19, BLURRY_IMAGE 10, FULL_FRAME_FALLBACK 8, BRIGHT_IMAGE 3, LOW_CONTRAST 1. Development and held-out test blocks are reported separately and were not used for calibration.
Phase 2 evidence verification: completed 2026-11-07 — the 12 committed panels in `docs/segmentation_audit/` were compared byte-for-byte with the pipeline-produced panels in `data/processed/segmentation_audit/seg-v2/panels/`. All 12 SHA-256 hashes match: Bacterial_leaf_blight__DSC_0365.png, Bacterial_leaf_blight__DSC_0703.png, Brown_spot__DSC_0121.png, Brown_spot__DSC_0105.png, Brown_spot__DSC_0114.png, Brown_spot__DSC_0109.png, Leaf_smut__DSC_0504.png, Leaf_smut__DSC_0501.png, Leaf_smut__DSC_0502.png, Leaf_smut__DSC_0511.png, Leaf_smut__DSC_0508.png, Leaf_smut__DSC_0515.png. Committed evidence set is exactly what the active `seg-v2` pipeline produced. No panels, manifest or summary were changed by this verification.
Current branch: main (local Phase 3 M1 work is uncommitted — Git is handled manually by the project owner)
Latest commit: 2a93073 — `docs(phase2): close verified seg-v2 evidence checkpoint` (Phase 2 evidence closure checkpoint).
LastPhase2CheckpointCommit: 2a93073
What works:
- Phase 1 data pipeline: audit manifest, near-duplicate review (13 groups / 27 images), frozen split protocol v1 (24-image singleton test + group-aware 5-fold CV), split invariant tests, audit notebook.
- Phase 2 M1: versioned YAML configs (`seg-v2`, `quality-v1`), strict validation, content hashing; `seg-v1` archived and still loadable.
- Phase 2 M2: EXIF-aware decode, no-stretch working image, margin crop, letterbox canvas, reversible `CanvasTransform`, denoise; quality metrics with separate warnings/rejections and leaf-mask-only exposure.
- Phase 2 M3: HSV+Lab leaf candidates, seeded K-Means merge, morphology, candidate scoring, ≥0.65 full-frame fallback, multi-leaf warning, `NO_CLEAR_LEAF_FOUND`.
- Phase 2 M4: leaf-relative lesion segmentation (hue/a*/b*/value shifts + K-Means), border exclusion, leaf-mask intersection, plausibility warning, and an explicit unreliable state when no healthy-green reference exists.
- Phase 2 M5: `vision/pipeline.py` (one stage composition + timings) and `vision/diagnostics.py` (4-up review panels).
- Phase 2 M6: 120/120 plausible leaf masks on the dataset (dev 96/96, held-out test 24/24), 0 rejected, 33 uncertain, 8 documented full-frame fallbacks, mean pipeline time 162.12 ms (p95 178.98 ms).
- Phase 2 M7: `docs/SEGMENTATION_NOTES.md` with the calibration before/after, committed curated seg-v2 panels + summary, notebook 02.
- Phase 3 M1: `backend/app/vision/feature_extraction.py` — one versioned extractor (colour, GLCM texture, shape, lesion, spatial; 50 features, `1.0.0`) with a machine-readable schema and `NaN`-not-zero handling of uncalibrated lesion estimates; `backend/tests/test_feature_extraction.py` locks the name/order contract.
What does not work:
- No dataset-wide feature matrix yet, no SVM/RF/KNN training, no model artifacts, no prediction API, no upload/history UI (Phase 3 M2 onward, then Phases 4–5).
- No segmentation ground-truth annotation exists, so "plausible mask" is a visual review, not an IoU score.
- A faint lesion band can remain on the dark lower edge of some Bacterial leaf blight strips; documented limitation, not fixed.
- Thresholds are calibrated on white-paper studio photos; phone photos with cluttered backgrounds are untested.
Next exact task: Phase 3 M2 — write `scripts/build_feature_matrix.py` to run `feature_extraction.extract_features` over all 120 images (development 96 / held-out test 24 reported separately, using the frozen `data/splits/`) and cache `data/processed/features_v1.csv` + `.npy` (git-ignored). Every row must carry `label`, `split`, `status`, `lesion_reliable`, `lesion_area_percentage`, `warnings`, `rejections`, `missing_features` and the schema/config provenance; uncalibrated lesion features stay `NaN` (no imputation, no silent zeros) and per-image failures are recorded, never filled. Also emit `feature_schema.json` with the same `1.0.0` names/order. Do not train any model in this step.

Phase 3 input contract (for all 120 known-disease images): the 120 images remain available for disease-classification work, but an `uncertain` lesion result must never silently become `0% lesion` or "healthy". Lesion reliability/uncertainty must be preserved explicitly for later feature handling and severity reporting.
Locked Phase 3 missing-value rule (decision P-13, recorded in `docs/DECISIONS.md` §4b and the `feature_extraction.py` module docstring): raw feature matrices preserve `NaN` values for unreliable lesion/spatial features. During later classifier training, missing-value imputation and missingness indicators must be fitted only on each training fold inside the scikit-learn pipeline. Uncertain lesion values must never be replaced with `0.0`, and images must not be silently dropped.
Documentation cleanup: removed the merge-duplicated lesion-area table row and the earlier duplicated "Commissioning note" / "Phase 2 evidence verification" blocks in `docs/SEGMENTATION_NOTES.md` §3; the only surviving verification block is the one naming checkpoint `2a93073`. No Phase 2 fact, hash, audit value, panel, config or segmentation code was changed, and the recorded Phase 3 M1 outcome is unchanged.

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
