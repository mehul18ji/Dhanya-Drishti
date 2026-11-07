# DhanyaDrishti — Dataset

> Raw data is **not** committed. This folder documents provenance, layout and the rules
> that keep training reproducible (PRD §18).

## 1. Layout

```text
data/
├── raw/
│   └── rice_leaf_diseases/
│       ├── Bacterial leaf blight/   40 images
│       ├── Brown spot/              40 images
│       └── Leaf smut/               40 images
├── processed/                       generated manifests, feature matrices (git-ignored)
└── splits/                          test.json, cv_folds.json, split_manifest.json
```

Original filenames and folder names are preserved. Original images are **never edited**;
all preprocessing happens in memory or on temporary copies.

## 2. Source

Approved dataset: [Kaggle — Rice Leaf Diseases](https://www.kaggle.com/datasets/vbookshelf/rice-leaf-diseases/data)
(`vbookshelf/rice-leaf-diseases`), 120 images, 3 classes, 40 each. All files are JPEG.

## 3. Verified characteristics (audited 2026-11-07)

| Class | Images | Resolution range | Notes |
|---|---:|---|---|
| Bacterial leaf blight | 40 | all 3081×897 | uniform batch — never use raw resolution as a feature |
| Brown spot | 40 | 286×88 – 3081×900 | includes tiny close-ups |
| Leaf smut | 40 | 250×71 – 4160×2340 | one large outlier |

- 120 files total, RGB, no exact duplicates (MD5).
- 13 images are >70 % leaf-green pixels (pure close-ups with no visible background).
- 9 images have a short side < 128 px (smallest 301×71).

## 4. Rules

1. Never commit `data/raw/` (see `.gitignore`).
2. Never modify originals; write derived data to `data/processed/`.
3. Splits are **fixed**: 24-image held-out test set (8 per class) plus stratified 5-fold CV on
   the remaining 96. Seed `42`. Manifests live in `data/splits/`.
4. Near-duplicate review must complete before splits are frozen (dHash-16 + HSV histogram + SSIM).
5. Any change to the split files invalidates previously reported metrics and requires retraining.

## 5. Limitations to state in every report

- No healthy-leaf class: the model cannot diagnose a leaf as healthy.
- No Mild/Moderate/Severe ground truth: severity is an experimental lesion-area estimate.
- 120 images is a small dataset; scores do not represent field reliability.
- Behaviour on smartphone photos, unusual lighting or multiple leaves may differ.
