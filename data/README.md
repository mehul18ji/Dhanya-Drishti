# DhanyaDrishti — Dataset

> Raw data is **not** committed. This folder documents provenance, layout and the rules
> that keep training reproducible (PRD §18). Full audit: [`docs/DATASET_AUDIT.md`](../docs/DATASET_AUDIT.md).

## 1. Layout

```text
data/
├── raw/
│   └── rice_leaf_diseases/
│       ├── Bacterial leaf blight/   40 images
│       ├── Brown spot/              40 images
│       └── Leaf smut/               40 images
├── processed/                       generated reports (git-ignored)
│   ├── dataset_manifest.csv
│   ├── dataset_audit.json
│   ├── near_duplicates.csv
│   ├── near_duplicate_summary.json
│   ├── near_duplicate_review.png
│   └── segmentation_audit/          Phase 2 renders (120 panels, summary JSON/CSV)
└── splits/                          frozen, committed
    ├── test.json
    ├── cv_folds.json
    ├── split_manifest.json
    └── duplicate_groups.json
```

Original filenames and folder names are preserved. Original images are **never edited**;
all preprocessing happens in memory or on temporary copies.

## 2. Source

Approved dataset: [Kaggle — Rice Leaf Diseases](https://www.kaggle.com/datasets/vbookshelf/rice-leaf-diseases/data)
(`vbookshelf/rice-leaf-diseases`), 120 images, 3 classes, 40 each, all JPEG/RGB.
Dataset version: **`ds-cc74ed659044`** (SHA-256 over sorted `md5 + path` pairs).

## 3. Verified characteristics (audited 2026-11-07)

| Class | Images | Resolution range | Notes |
|---|---:|---|---|
| Bacterial leaf blight | 40 | all 3081×897 | single resolution — never use raw resolution as a feature |
| Brown spot | 40 | 286×88 – 3081×900 | includes tiny close-ups |
| Leaf smut | 40 | 250×71 – 4160×2340 | includes one large outlier |

- 120 files, 37.9 MB, no decode failures, no exact duplicates (MD5).
- 9 images have a short side < 128 px (smallest 301×71) → hard size gate is 64 px, not 256 px.
- 11 images are >70 % leaf-green (background-free close-ups) → segmentation needs a
  full-frame fallback at ≥0.65.
- 10 images carry EXIF orientation `3` (180°) → orientation correction is mandatory.
- White paper backgrounds dominate global exposure statistics → over-exposure must be
  measured inside the leaf mask.
- **13 confirmed near-duplicate groups covering 27 images (22.5 %)**. No image is excluded;
  splits keep each group together (see `splits/duplicate_groups.json`).

## 4. Frozen splits

| Property | Value |
|---|---|
| Seed | 42 |
| Test | 24 images, 8 per class, singleton images only |
| Cross-validation | 96 images, stratified 5-fold, group-aware |
| Reproducibility | `python scripts/make_splits.py --verify` |

## 5. Regeneration commands

```powershell
python scripts/audit_dataset.py            # manifest + audit summary
python scripts/find_near_duplicates.py     # candidate pairs + review sheet
python scripts/build_duplicate_groups.py   # confirmed groups (after visual review)
python scripts/make_splits.py              # test.json + cv_folds.json + manifest
python -m pytest tests -q                  # split invariants
```

## 6. Rules

1. Never commit `data/raw/` (see `.gitignore`).
2. Never modify originals; write derived data to `data/processed/`.
3. Splits are fixed. Any change to `test.json` / `cv_folds.json` invalidates previously
   reported metrics and requires retraining.
4. A confirmed duplicate group must never be split across train/validation/test.
5. Record a dataset checksum and the seed for every experiment.

## 7. Limitations to state in every report

- No healthy-leaf class: the model cannot diagnose a leaf as healthy.
- No Mild/Moderate/Severe ground truth: severity is an experimental lesion-area estimate.
- Effective visual diversity is lower than 120 because of the 13 duplicate groups.
- 120 images is a small dataset; scores do not represent field reliability.
