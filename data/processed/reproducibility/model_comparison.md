# Model comparison — feature set v1.0.0

Generated `2026-11-09T14:43:43+00:00` | seed 42 | development rows 96 | held-out rows 24

Selection metric: **mean cross-validated macro F1** on the 96 development rows, cross-validated and grid-searched only on the frozen manifest folds (`cv_fold` 0–4, replayed with `PredefinedSplit`). No splitter is generated.

## Cross-validation (development rows only)

| model | accuracy | balanced acc. | macro precision | macro recall | macro F1 | macro F1 std |
|---|---:|---:|---:|---:|---:|---:|
| svm | 0.8437 | 0.8397 | 0.8693 | 0.8397 | 0.8412 | 0.0604 |
| random_forest | 0.8016 | 0.7984 | 0.8277 | 0.7984 | 0.7935 | 0.0387 |
| knn | 0.7611 | 0.7571 | 0.8253 | 0.7571 | 0.7507 | 0.0853 |

## Out-of-fold confusion matrices

### svm

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 27 | 2 | 3 |
| brown_spot | 3 | 26 | 3 |
| leaf_smut | 0 | 4 | 28 |

Per-class:

| class | precision | recall | F1 | support |
|---|---:|---:|---:|---:|
| bacterial_leaf_blight | 0.9000 | 0.8438 | 0.8710 | 32 |
| brown_spot | 0.8125 | 0.8125 | 0.8125 | 32 |
| leaf_smut | 0.8235 | 0.8750 | 0.8485 | 32 |

### random_forest

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 29 | 2 | 1 |
| brown_spot | 4 | 24 | 4 |
| leaf_smut | 3 | 5 | 24 |

Per-class:

| class | precision | recall | F1 | support |
|---|---:|---:|---:|---:|
| bacterial_leaf_blight | 0.8056 | 0.9062 | 0.8529 | 32 |
| brown_spot | 0.7742 | 0.7500 | 0.7619 | 32 |
| leaf_smut | 0.8276 | 0.7500 | 0.7869 | 32 |

### knn

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 28 | 3 | 1 |
| brown_spot | 9 | 21 | 2 |
| leaf_smut | 4 | 4 | 24 |

Per-class:

| class | precision | recall | F1 | support |
|---|---:|---:|---:|---:|
| bacterial_leaf_blight | 0.6829 | 0.8750 | 0.7671 | 32 |
| brown_spot | 0.7500 | 0.6562 | 0.7000 | 32 |
| leaf_smut | 0.8889 | 0.7500 | 0.8136 | 32 |

## Selected model

**svm** chosen by mean CV macro F1 (0.8412 ± 0.0604). Final hyperparameters: `{"model__C": 1.0, "model__gamma": "scale"}`.

## Held-out evaluation (once, after selection)

**Not run in this report.** This is a development-only run: the 24 held-out rows were not read, fitted on or predicted. The single held-out evaluation recorded earlier is restated in `PROJECT_STATUS.md` and is not recomputed.

## Caveats

Scores come from 96 development rows and 24 held-out rows of one small, visually similar 3-class dataset with no healthy class. They are optimistically biased by dataset size and near-duplicate similarity and are **not** a real-world accuracy claim. Severe/uncertain handling is a Phase 4 concern; nothing here is validated on field photographs.
