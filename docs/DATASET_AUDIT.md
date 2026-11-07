# Dataset Audit — Phase 1

> Executed 2026-11-07 against the approved Kaggle Rice Leaf Diseases dataset
> (`rice_leaf_diseases`, 120 images, 3 classes).
>
> Dataset version: **`ds-cc74ed659044`**
> Dataset checksum (SHA-256 over sorted `md5 + path` pairs): recorded in
> `data/processed/dataset_audit.json` and `data/splits/split_manifest.json`.
>
> Reproduce everything with:
>
> ```powershell
> python scripts/audit_dataset.py
> python scripts/find_near_duplicates.py
> python scripts/build_duplicate_groups.py
> python scripts/make_splits.py
> python -m pytest tests -q
> ```

Raw images live in `data/raw/rice_leaf_diseases/` and are **not committed**. They are never
modified by any script.

---

## 1. Inventory

| Metric | Value |
|---|---|
| Images | 120 |
| Classes | 3 × 40 |
| Total size | 37.9 MB |
| Format / mode | JPEG / RGB (all 120) |
| Decode failures | 0 |
| Exact MD5 duplicates | 0 |
| EXIF orientations | 1 (110 images), 3 (10 images) |

Class counts match the PRD exactly: Bacterial Leaf Blight 40, Brown Spot 40, Leaf Smut 40.

## 2. Resolution and aspect ratio

| Class | Width | Height | Aspect | Distinct resolutions |
|---|---|---|---|---|
| Bacterial Leaf Blight | 3081 | 897 | 3.43 | **1** |
| Brown Spot | 286 – 3081 | 88 – 900 | 1.33 – 5.30 | 20 |
| Leaf Smut | 250 – 4160 | 71 – 2340 | 1.25 – 5.03 | 16 |

**Leakage warning:** every Bacterial Leaf Blight image has the identical resolution
3081×897. Raw width, height, aspect or file size must never be used as model features —
they would partially encode the label. All geometry must be normalised to the processing
canvas (ratios, not pixels).

**Shape warning:** aspect ratios reach 5.30:1. Leaf/candidate scoring must not prefer
"square" regions; it must prefer large area with a mild centrality bonus.

## 3. Small images

Nine images have a short side below 128 px:

| Image | Size |
|---|---|
| `Leaf smut/DSC_0502.jpg` | 301 × 71 |
| `Leaf smut/DSC_0501.jpg` | 367 × 73 |
| `Leaf smut/DSC_0500.jpg` | 376 × 80 |
| `Brown spot/DSC_0114.jpg` | 296 × 88 |
| `Brown spot/DSC_0115.jpg` | 286 × 92 |
| `Brown spot/DSC_0116.jpg` | 340 × 94 |
| `Brown spot/DSC_0117.jpg` | 467 × 104 |
| `Brown spot/DSC_0110.jpg` | 456 × 124 |
| `Brown spot/DSC_0111.jpg` | 316 × 127 |

Cumulative counts: 19 images below 224 px, 25 below 256 px, 28 below 300 px.

**Consequence:** the PRD's "image too small" check must not use a naive 256 px minimum.
Planned Phase 2 policy (to be confirmed in code/config):

- hard reject: short side **< 64 px**
- soft warning: short side **< 224 px**
- the 9 images above must still be analysable.

## 4. Full-frame close-ups

Counts by leaf-green fraction (HSV: H 25–95, S ≥ 40, V ≥ 25):

| Threshold | Images |
|---|---:|
| > 0.60 | 21 |
| > 0.65 | 15 |
| > 0.70 | 11 |
| > 0.75 | 9 |
| > 0.80 | 8 |

Eleven images exceed 0.70 (listed in `dataset_audit.json`). Examples:
`Leaf smut/DSC_0510.jpg` (0.90), `Brown spot/DSC_0111.jpg` (0.95).

**Consequence:** a leaf detector that requires visible background will reject these images.
Phase 2 must implement a documented fallback: when the leaf-like fraction is high
(starting threshold **0.65**), treat the whole frame as the leaf mask and record a warning.
Calibrate the exact threshold in Phase 2 and record it in `configs/segmentation.yaml`.

## 5. EXIF orientation

Ten images carry EXIF orientation `3` (180° rotation). All are 3081×897:

`DSC_0367`, `DSC_0324`, `DSC_0312`, `DSC_0313`, `DSC_0314`, `DSC_0315`, `DSC_0318`,
`DSC_0319`, `DSC_0320`, `DSC_0321`.

**Consequence:** EXIF orientation correction is mandatory in Stage A preprocessing. Without
it, those leaves are analysed upside-down. One of them (`DSC_0367.JPG`) is in the held-out
test set, so the evaluation exercises this path.

## 6. Quality metric percentiles (measured at 400 px long side)

| Metric | p5 | p25 | p50 | p75 | p95 |
|---|---:|---:|---:|---:|---:|
| Mean brightness (V) | 155.5 | 186.8 | 198.5 | 205.7 | 221.6 |
| Over-exposed fraction (V ≥ 245) | 0.000 | 0.000 | 0.000 | 0.152 | 0.643 |
| Laplacian variance (blur) | 87.0 | 157.1 | 232.4 | 381.3 | 943.9 |
| Leaf-green fraction | 0.200 | 0.271 | 0.380 | 0.518 | 0.812 |

**Consequence:** global over-exposure is dominated by the white paper background (up to 64%
of pixels at p95). The over-exposure check must be computed **inside the leaf mask**, not on
the whole frame. The blur and brightness percentiles are the calibration inputs for
`configs/quality_thresholds.yaml`.

## 7. Near-duplicate review

Exact MD5 duplicates: **none**.

A coarse 8×8 average hash produced 298 false "matches" because every image shares the same
leaf-on-paper composition, so the review used a stricter, multi-signal screen
(`scripts/find_near_duplicates.py`):

1. dHash 16×16 (256-bit)
2. HSV histogram correlation
3. SSIM on a 256×256 grey canvas
4. ORB keypoints + RANSAC homography inliers (catches same-leaf, re-framed shots that SSIM misses)

All 7,140 pairs were screened with ORB; 186 pairs had reportable evidence. The candidate rule
was:

```text
dhash_hamming <= 10
OR (orb_inliers >= 5 AND orb_inlier_ratio >= 0.80)
OR (ssim >= 0.97 AND hist_correlation >= 0.98)
```

17 candidates were reviewed visually. **15 pair relationships were confirmed as the same
scene; 2 were rejected as different leaves.** The confirmed set forms **13 groups covering
27 images (22.5% of the dataset)**:

| Group | Class | Images |
|---|---|---|
| `dup-bacterial_leaf_blight-01` | Bacterial Leaf Blight | DSC_0365, DSC_0366 |
| `dup-bacterial_leaf_blight-02` | Bacterial Leaf Blight | DSC_0375, DSC_0376 |
| `dup-brown_spot-01` | Brown Spot | DSC_0299, DSC_0300 |
| `dup-brown_spot-02` | Brown Spot | DSC_0302, DSC_0303 |
| `dup-brown_spot-03` | Brown Spot | DSC_0306, DSC_0307 |
| `dup-leaf_smut-01` | Leaf Smut | DSC_0308, DSC_0309 |
| `dup-leaf_smut-02` | Leaf Smut | DSC_0312, DSC_0313 |
| `dup-leaf_smut-03` | Leaf Smut | DSC_0314, DSC_0315 |
| `dup-leaf_smut-04` | Leaf Smut | DSC_0318, DSC_0319 |
| `dup-leaf_smut-05` | Leaf Smut | DSC_0321, DSC_0322 (and DSC_0320, verified by warping) |
| `dup-leaf_smut-06` | Leaf Smut | DSC_0335, DSC_0336 |
| `dup-leaf_smut-07` | Leaf Smut | DSC_0338, DSC_0339 |
| `dup-leaf_smut-08` | Leaf Smut | DSC_0504, DSC_0512 |

Rejected candidates (different leaves despite ORB matches):

- `Bacterial leaf blight/DSC_0395.JPG` vs `DSC_0405.JPG`
- `Bacterial leaf blight/DSC_0372.JPG` vs `DSC_0396.JPG`

Evidence for every confirmed pair (hashes, histogram, SSIM, ORB counts) is stored in
`data/splits/duplicate_groups.json`. Every pair meets `orb_inliers ≥ 5` and
`orb_inlier_ratio ≥ 0.80`. The review sheet is
`data/processed/near_duplicate_review.png`; the raw pair table is
`data/processed/near_duplicates.csv`.

**Decision:** no image is excluded. Duplicates are retained (the approved dataset is 120
images) but are kept together by the split protocol.

## 8. Frozen splits

| Property | Value |
|---|---|
| Split version | `v1` |
| Seed | 42 |
| Held-out test | 24 images (8 per class) |
| Cross-validation | 96 images (32 per class), stratified 5-fold |
| Group-aware | Yes (`StratifiedGroupKFold`) |
| Test duplicates | None — test is built only from singleton images |
| Group split across folds | None |

Per-fold validation sizes: 20, 19, 19, 19, 19 (each fold contains all three classes).

The held-out test set deliberately includes difficult cases: 2 tiny images (one 301×71),
3 background-free close-ups, and 1 EXIF-rotated image.

All invariants are asserted both in `scripts/make_splits.py` and in
`tests/test_split_manifests.py` (6 tests). Reproducibility is checked with:

```powershell
python scripts/make_splits.py --verify
```

Files:

- `data/splits/test.json` — 24 items with path, label, md5
- `data/splits/cv_folds.json` — 5 folds with exact train/validation path lists
- `data/splits/split_manifest.json` — counts, hashes, dataset version, invariants
- `data/splits/duplicate_groups.json` — confirmed groups + rejected candidates

## 9. Consequences for Phase 2 and Phase 3

| Finding | Required implementation response |
|---|---|
| 11 background-free close-ups | full-frame leaf fallback at ≥0.65 green ratio |
| 9 tiny images | hard size gate 64 px, soft warning 224 px |
| EXIF orientation 3 | apply EXIF orientation before any processing |
| White paper backgrounds | quality checks computed inside the leaf mask |
| Aspect ratios to 5.3:1 | area/centrality candidate scoring; no squareness bias |
| BLB single resolution | never use raw resolution/byte size as a feature |
| 13 duplicate groups | group-aware CV; singleton-only test; report the overlap honestly |
| 120 images | report CV variance, per-class metrics and baselines, never a single accuracy |

## 10. Known limitations

1. No healthy class, no severity labels, no expert annotations — the system cannot diagnose
   health or validate severity.
2. Duplicate groups mean effective sample diversity is lower than 120; the true independent
   count is roughly 106 scenes.
3. All images are photographed under controlled, similar conditions; smartphone photos,
   field lighting and cluttered backgrounds remain untested until Phase 6.
4. Near-duplicate review was visual on one screen; borderline pairs could exist below the
   candidate threshold. Re-run the screen if the dataset changes.
5. Dataset checksums are tied to the exact file bytes; any re-download or re-encoding changes
   `dataset_version` and requires regenerating the splits and retraining.
