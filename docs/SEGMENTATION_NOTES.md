# Segmentation Notes — Phase 2

> Evidence file for PRD §25 Phase 2 and `PHASE_PLAN.txt` milestone M6/M7.
> Produced by `python scripts/run_segmentation_audit.py` on the full 120-image dataset.
> Raw data is never modified and never committed.

---

## 1. Configuration under audit

| Item | Value |
|---|---|
| Segmentation config | `seg-v2` |
| Segmentation config SHA-256 | `c3784f11df53d13d4db515b1a11b36fd9b1bfbe34777de1d99ad2380a4a1bba1` |
| Quality config | `quality-v1` |
| Quality config SHA-256 | `c4cfe9e2f911…` (full hash in `data/processed/segmentation_audit/seg-v2/segmentation_audit.json`) |
| K-Means seeds | `42` (leaf and lesion), `n_init = 10` |
| Canvas | letterboxed 512 px, working image 768 px long side |
| Superseded config | `backend/configs/archive/segmentation.seg-v1.yaml` (retained, still loadable) |

Every threshold quoted in this file lives in `backend/configs/*.yaml`; no number is
hard-coded in a segmentation module.

## 2. Split discipline (why the audit is reported twice)

Split protocol v1 is frozen (`docs/DECISIONS.md` E-17): 24 held-out test images (8 per
class, singleton images only) and 96 development images (group-aware stratified 5-fold CV).

- **Development images (96)** are the only images used to judge the pipeline and to
  justify any threshold change.
- **Held-out test images (24)** are reported for honesty only. No calibration decision in
  this phase looked at them; the numbers below are listed separately so that stays
  auditable.

The audit therefore reports `development` and `held_out_test` counts separately rather
than one blended figure.

## 3. Audit result — `seg-v2`

| Outcome | All 120 | Development (96) | Held-out test (24) |
|---|---:|---:|---:|
| Plausible leaf mask | 120 (100 %) | 96 | 24 |
| Clean (no warnings) | 87 | 71 | 16 |
| Uncertain (warnings) | 33 | 25 | 8 |
| Rejected | 0 | 0 | 0 |
| Full-frame fallback applied | 8 | 7 | 1 |
| Multiple leaves detected | 0 | 0 | 0 |
| Lesion estimate marked unreliable | 0 | 0 | 0 |

Per class:

| Class | Images | Leaf ok | Clean | Uncertain | Rejected | Fallback |
|---|---:|---:|---:|---:|---:|---:|
| Bacterial leaf blight | 40 | 40 | 37 | 3 | 0 | 0 |
| Brown spot | 40 | 40 | 23 | 17 | 0 | 4 |
| Leaf smut | 40 | 40 | 27 | 13 | 0 | 4 |

Warning histogram (one image may raise several):

| Code | Count | Meaning |
|---|---:|---|
| `SMALL_IMAGE` | 19 | short side < 224 px (soft warning, analysis continues) |
| `BLURRY_IMAGE` | 10 | Laplacian variance < 40 on the working image |
| `FULL_FRAME_FALLBACK` | 8 | leaf fills the frame; whole image treated as leaf |
| `BRIGHT_IMAGE` | 3 | mean V > 230 |
| `LOW_CONTRAST` | 1 | std V < 16 |
| Rejections | 0 | every dataset image is a real, analysable leaf photo |

Timing on CPU (whole pipeline, one image):

| mean | p50 | p95 | max |
|---:|---:|---:|---:|
| 130.6 ms | 117.4 ms | 138.3 ms | 1 579 ms (first image, cold start) |

Lesion-area estimate (`lesion_pixels / leaf_pixels × 100`), all 120 images:

| mean | p50 | p95 |
|---:|---:|---:|
| 13.71 % | 10.45 % | 39.90 % |

> **Phase 2 gate:** "≥ 110/120 dataset images produce a plausible leaf mask" — met at
> 120/120. "The rest are rejected with a reason or use the documented full-frame
> fallback" — 8 use the documented fallback; no image needed rejection because the
> dataset contains only photographable leaves. Rejection behaviour itself is proven by
> `tests/test_leaf_segmentation.py::test_non_leaf_image_is_not_forced_into_a_prediction`
> and `tests/test_vision_pipeline.py::test_non_leaf_image_is_rejected_without_lesion_stage`.

## 4. Calibration record: `seg-v1` → `seg-v2`

`seg-v1` was run first over the same 120 images
(`data/processed/segmentation_audit/baseline-seg-v1/`, git-ignored) and every panel was
inspected. Three corrections were made, each tied to a visually verified systematic
failure — not to the audit score.

### 4.1 Warm paper shadow merged into the leaf mask (40 Bacterial leaf blight images)

- **Pattern:** the leaf mask extended past the leaf into the soft warm shadow on the
  paper; the lesion stage then reported that shadow band as lesion tissue along the
  bottom edge of the leaf — a false severity increase in the class with the most
  uniform scan batch.
- **Measurement:** shadow pixels sit at Lab chroma 9–13 (`|a−128| + |b−128|`), real leaf
  tissue at 40+. `seg-v1` `leaf.lab.min_chroma = 10` therefore admitted paper.
- **Change:** `leaf.lab.min_chroma 10 → 20`.
- **Effect:** 37 images change leaf area by more than 5 percentage points; mean leaf
  area fraction 0.539 → 0.494; no image loses its leaf; the same images that were
  previously rejected as "no leaf" are still detected.
- **Verified:** `docs/segmentation_audit/Bacterial_leaf_blight__DSC_0365.png` and
  `…_DSC_0703.png` (mask now follows the leaf edge).

### 4.2 A fully necrotic leaf was reported as "0 % lesions"

- **Pattern:** when a leaf had almost no healthy green tissue, the relative-colour
  lesion stage used the leaf's own necrotic tissue as the "healthy" reference, so nothing
  looked like a lesion. The result was a confident 0 % — the opposite of honest.
- **Change:** new `lesion.min_healthy_reference_fraction = 0.01` plus a code path that
  marks the estimate unreliable (`reliable = False`,
  `LESION_REFERENCE_UNAVAILABLE` + `WEAK_LESION_MASK`) instead of returning a number the
  pipeline cannot support. Phase 4 turns this into the `uncertain` state (PRD §11).
- **Verified:** `tests/test_lesion_segmentation.py::test_necrotic_leaf_without_healthy_reference_is_unreliable`.
  No dataset image triggers it (0/120), which is expected — the dataset has no fully
  necrotic leaf — so this is a guard for real user uploads, not a calibration tweak.

### 4.3 Leaf-edge shading counted as lesion along the whole outline

- **Pattern:** after 4.1, a thin lesion band still followed the leaf outline on the
  long strip images; 6 px at the 512-px canvas is roughly where anti-aliased/shaded leaf
  edge tissue lives.
- **Change:** `lesion.border_exclusion_px 2 → 6` (the value the phase plan proposed as a
  starting point).
- **Effect (development images):** −3 to −11 percentage points of lesion area; genuine
  spots are retained (`docs/segmentation_audit/Brown_spot__DSC_0105.png`), and a lightly
  smutted leaf moved from 8.0 % to 1.7 %
  (`data/processed/segmentation_audit/_experiments/`, git-ignored comparison).

### 4.4 Before / after summary (all 120 images)

| Metric | `seg-v1` | `seg-v2` |
|---|---:|---:|
| Plausible leaf masks | 120 | 120 |
| Rejected / uncertain / clean | 0 / 33 / 87 | 0 / 33 / 87 |
| Mean leaf area fraction | 0.539 | 0.494 |
| Mean lesion area | 25.47 % | 13.71 % |
| Median lesion area | 21.57 % | 10.45 % |
| p95 lesion area | 51.08 % | 39.90 % |
| BLB mean lesion area | 31.86 % | 16.77 % |
| Brown spot mean lesion area | 22.00 % | 12.98 % |
| Leaf smut mean lesion area | 22.57 % | 11.37 % |
| Images with 0 % lesion | 0 | 0 |
| Mean pipeline time | 134.3 ms | 130.6 ms |

The halved lesion area is the intended outcome: `seg-v1` was measuring shadow, not
disease. `seg-v2` numbers are still an **experimental visible-lesion estimate**, not
agronomic severity (PRD §12).

No threshold was changed just to increase the pass rate; the pass rate was already
120/120 before calibration. No calibration decision used the held-out test images.

## 5. Curated visual evidence set

Committed under `docs/segmentation_audit/` (12 panels, ~2.1 MB). Each panel is 4-up:
letterboxed input canvas, leaf mask, lesion mask, overlay. The full 120-image render set
stays in the git-ignored `data/processed/segmentation_audit/seg-v2/panels/`.

| Panel | Why it is included |
|---|---|
| `Bacterial_leaf_blight__DSC_0365.png` | BLB at the dominant 3.4:1 strip resolution; the image whose shadow leak drove 4.1 |
| `Bacterial_leaf_blight__DSC_0703.png` | Second BLB leaf — confirms BLB is not one template |
| `Brown_spot__DSC_0121.png` | Near-square frame (1.33:1) |
| `Brown_spot__DSC_0105.png` | Dataset's most extreme aspect ratio (5.3:1); real spots retained after 4.3 |
| `Brown_spot__DSC_0114.png` | Tiny image (296×88) — `SMALL_IMAGE` warning path |
| `Brown_spot__DSC_0109.png` | Background-free close-up — full-frame fallback |
| `Leaf_smut__DSC_0504.png` | Near-square smut frame (1.25:1) |
| `Leaf_smut__DSC_0501.png` | 5.0:1 strip |
| `Leaf_smut__DSC_0502.png` | Smallest image in the dataset (301×71) |
| `Leaf_smut__DSC_0511.png` | Background-free close-up — full-frame fallback |
| `Leaf_smut__DSC_0508.png` | Pure leaf close-up named in the phase plan |
| `Leaf_smut__DSC_0515.png` | Pure leaf close-up named in the phase plan |

`curated_manifest.json` records the source path and reason for each panel;
`audit_summary.json` is the committed aggregate summary. The panels are regenerated
byte-identically by the documented command below (same machine/library versions).

## 6. Known limitations (carry into Phase 3 and the model card)

1. **Edge band on some BLB strips.** After 4.3 a faint lesion band can remain on the
   leaf's own dark lower edge (`Bacterial_leaf_blight__DSC_0373.png`). It is included in
   the lesion-area estimate and therefore in the experimental severity.
2. **Border exclusion trades recall for precision.** Marginal lesions lose their outer
   6 px; small lesions that lie entirely inside that band would be missed.
3. **Thresholds are calibrated on a white-paper studio dataset.** Phone photos with
   cluttered backgrounds are untested; `lab.min_chroma = 20` may exclude pale or
   back-lit leaves. Ranges stay in YAML so they can be revisited.
4. **The 0.65 green-ratio fallback is a heuristic.** Eight dataset images are analysed as
   "the whole frame is leaf"; findings there are still warnings-only (`FULL_FRAME_FALLBACK`),
   and the Phase 4 API must surface that state as `uncertain`.
5. **No multi-leaf example exists in the dataset**, so the multi-leaf warning is proven
   only by the synthetic test. A real two-leaf photo is part of the Phase 6 manual matrix.
6. **Heavily smutted close-ups** legitimately reach 55–65 % lesion coverage; values near
   the 65 % plausibility guard can be flagged `WEAK_LESION_MASK` even when the mask is
   correct.
7. **Leaf masks are not compared to expert ground truth** — there is no segmentation
   annotation for this dataset. "Plausible" means visually reviewed against the original,
   which is weaker than an IoU score and must be described that way in the model card.
8. **Lesion colours are relative to the leaf's healthy tissue**, so a leaf with no
   healthy tissue cannot be scored (`LESION_REFERENCE_UNAVAILABLE`, `uncertain`).

## 7. Regenerate everything

```powershell
# from the repository root
python scripts/audit_dataset.py            # Phase 1 manifest (needed for the image list)
python scripts/run_segmentation_audit.py   # seg-v2 audit + curated docs set
python -m pytest backend/tests -q          # 70 tests
```

Useful variants:

```powershell
python scripts/run_segmentation_audit.py --only leaf_smut --limit 5   # quick spot-check
python scripts/run_segmentation_audit.py --no-curated --no-panels     # numbers only
python scripts/run_segmentation_audit.py --label baseline-seg-v1 \
    --config backend/configs/archive/segmentation.seg-v1.yaml         # re-create a baseline
```

Outputs:

| Path | Committed | Contents |
|---|---|---|
| `data/processed/segmentation_audit/seg-v2/segmentation_audit.json` | no | per-image rows + aggregates + timings |
| `data/processed/segmentation_audit/seg-v2/segmentation_audit.csv` | no | per-image rows |
| `data/processed/segmentation_audit/seg-v2/panels/` | no | 120 review panels |
| `docs/segmentation_audit/*.png` | yes | curated 12-panel evidence set |
| `docs/segmentation_audit/audit_summary.json` | yes | committed aggregate summary |
| `docs/segmentation_audit/curated_manifest.json` | yes | curated selection + reasons |

## 8. What Phase 3 inherits

- `vision/pipeline.py::run_segmentation` is the single entry point for training-feature
  generation and later inference — no second copy of the stage order.
- `SegmentationPipelineResult.quality` already separates warnings from rejections; the
  Phase 4 API maps `rejected → rejected`, `uncertain (or lesion unreliable) → uncertain`,
  otherwise `predicted`.
- The lesion mask is produced on the 512-px letterboxed canvas, so lesion-area features
  are scale-invariant by construction (PRD §9 Stage E, decision R3).
- Raw resolution is never used by any segmentation input, so the BLB 3081×897 shortcut
  cannot leak into the feature vector.
