# Model evaluation — feature set v1.0.0

Generated `2026-11-09T14:44:05+00:00` | development run `run_20261107T175000Z_svm`

This report restates the frozen Phase 3 M3 results and adds honest baselines. It trains nothing, predicts nothing, and does not recompute the held-out evaluation.

## Provenance

- feature set version: **1.0.0**
- segmentation config: `seg-v2` (sha256 `c3784f11df53...`)
- quality config: `quality-v1` (sha256 `c4cfe9e2f911...`)
- split protocol: **v1** (seed 42)
- dataset version: `ds-cc74ed659044`

## Baseline reference points (development only)

- **majority class**: always predict the most frequent development class.
- **stratified random**: deterministic draw from the development class prior with a fixed seed.

| baseline | accuracy | balanced acc. | macro precision | macro recall | macro F1 |
|---|---:|---:|---:|---:|---:|
| majority (bacterial_leaf_blight) | 0.3333 | 0.3333 | 0.1111 | 0.3333 | 0.1667 |
| stratified random (seed 42) | 0.2396 | 0.2396 | 0.2384 | 0.2396 | 0.2390 |

Development label distribution: `bacterial_leaf_blight` 32, `brown_spot` 32, `leaf_smut` 32

## Development — models (frozen manifest folds)

| model | CV macro F1 | std | CV accuracy | CV balanced acc. | OOF macro F1 |
|---|---:|---:|---:|---:|---:|
| svm | 0.8412 | 0.0604 | 0.8437 | 0.8397 | 0.8440 |
| random_forest | 0.7935 | 0.0387 | 0.8016 | 0.7984 | 0.8006 |
| knn | 0.7507 | 0.0853 | 0.7611 | 0.7571 | 0.7602 |

Selected model: **svm** by mean CV macro F1 (0.8412 ± 0.0604); hyperparameters `{"model__C": 1.0, "model__gamma": "scale"}`.

### Out-of-fold confusion matrices (development)

**svm**

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 27 | 2 | 3 |
| brown_spot | 3 | 26 | 3 |
| leaf_smut | 0 | 4 | 28 |

**random_forest**

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 29 | 2 | 1 |
| brown_spot | 4 | 24 | 4 |
| leaf_smut | 3 | 5 | 24 |

**knn**

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 28 | 3 | 1 |
| brown_spot | 9 | 21 | 2 |
| leaf_smut | 4 | 4 | 24 |

## Held-out — single final evaluation (restated, not recomputed)

Source: `run_20261107T173626Z_svm` — Evaluated exactly once after selection on the pre-correction run whose fitted pipeline is identical to the corrected one. Restated verbatim; not recomputed, not tuned against, not overwritten by this report.

| accuracy | balanced acc. | macro precision | macro recall | macro F1 | n |
|---:|---:|---:|---:|---:|---:|
| 0.7917 | 0.7917 | 0.8059 | 0.7917 | 0.7855 | 24 |

| true \ predicted | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| bacterial_leaf_blight | 6 | 1 | 1 |
| brown_spot | 1 | 5 | 2 |
| leaf_smut | 0 | 0 | 8 |

Per-image predictions (stored rows, not regenerated):

| image | true | predicted | correct |
|---|---|---|:---:|
| bacterial_leaf_blight__DSC_0367 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0373 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0377 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0382 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0385 | bacterial_leaf_blight | brown_spot | no |
| bacterial_leaf_blight__DSC_0396 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0404 | bacterial_leaf_blight | bacterial_leaf_blight | yes |
| bacterial_leaf_blight__DSC_0702 | bacterial_leaf_blight | leaf_smut | no |
| brown_spot__DSC_0108 | brown_spot | brown_spot | yes |
| brown_spot__DSC_0117 | brown_spot | brown_spot | yes |
| brown_spot__DSC_0119 | brown_spot | brown_spot | yes |
| brown_spot__DSC_0304 | brown_spot | brown_spot | yes |
| brown_spot__DSC_0324 | brown_spot | leaf_smut | no |
| brown_spot__DSC_0325 | brown_spot | leaf_smut | no |
| brown_spot__DSC_0333 | brown_spot | bacterial_leaf_blight | no |
| brown_spot__DSC_0337 | brown_spot | brown_spot | yes |
| leaf_smut__DSC_0316 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0327 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0328 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0331 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0502 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0503 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0507 | leaf_smut | leaf_smut | yes |
| leaf_smut__DSC_0509 | leaf_smut | leaf_smut | yes |

| class | precision | recall | F1 | support |
|---|---:|---:|---:|---:|
| bacterial_leaf_blight | 0.8571 | 0.7500 | 0.8000 | 8 |
| brown_spot | 0.8333 | 0.6250 | 0.7143 | 8 |
| leaf_smut | 0.7273 | 1.0000 | 0.8421 | 8 |

## Verification

- development predictions re-scored against recorded metrics: svm=yes, random_forest=yes, knn=yes
- held-out image ids overlap development ids: no
- held-out results recomputed by this report: no
- held-out prediction rows restated from the stored artifact: 24
- models trained or tuned by this report: no

## Limitations

- 96 development images and 24 held-out images from one small, visually similar 3-class dataset. Scores are optimistically biased by dataset size and near-duplicate similarity and are not a real-world accuracy claim.
- There is no healthy-leaf class. The system predicts only Bacterial Leaf Blight, Brown Spot and Leaf Smut and must never be described as a diseased/healthy classifier.
- Severity is an experimental lesion-area estimate and is always shown with its disclaimer; nothing in this report validates severity clinically.
- The selected SVM pipeline exposes no calibrated probabilities, so confidence handling remains a Phase 4 decision.
- Baselines and models are scored on the same development labels; they are reference points, not independent replications.
- The single 24-image held-out evaluation is restated, not repeated: its sampling noise is roughly +/-0.05-0.08 macro F1 and is stated rather than explained away.

