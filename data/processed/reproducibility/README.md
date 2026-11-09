# Reproducibility snapshots

Small, tracked copies of the numerical development artifacts used for the report,
model comparison, feature-schema checks, and evaluation verification.

These files are **snapshots**, not the working artifacts. The full, git-ignored
development outputs live one level up under `data/processed/`:

| Snapshot | Full working artifact (ignored) |
|---|---|
| `dataset_manifest.csv` | `data/processed/dataset_manifest.csv` |
| `dataset_audit.json` | `data/processed/dataset_audit.json` |
| `near_duplicates.csv` | `data/processed/near_duplicates.csv` |
| `near_duplicate_summary.json` | `data/processed/near_duplicate_summary.json` |
| `segmentation_audit.csv` | `data/processed/segmentation_audit/seg-v2/segmentation_audit.csv` |
| `segmentation_audit_summary.json` | `summary` block of `data/processed/segmentation_audit/seg-v2/segmentation_audit.json` |
| `feature_matrix.json` | `data/processed/features/feature_set_v1.0.0/feature_matrix.json` |
| `feature_matrix_summary.md` | `data/processed/features/feature_set_v1.0.0/feature_matrix_summary.md` |
| `model_comparison.json` | `data/processed/training_runs/run_20261107T175000Z_svm/model_comparison.json` |
| `model_comparison.md` | `data/processed/training_runs/run_20261107T175000Z_svm/model_comparison.md` |
| `cv_predictions.csv` | `data/processed/training_runs/run_20261107T175000Z_svm/cv_predictions.csv` |
| `evaluation_report.json` | `data/processed/training_runs/evaluation/evaluation_report.json` |
| `evaluation_report.md` | `data/processed/training_runs/evaluation/evaluation_report.md` |

Deliberately **not** tracked here:

- `feature_matrix.csv` (the 120-row numerical matrix; it stays in the ignored
  working tree so the 24 held-out feature vectors are not committed);
- `held_out_predictions.csv` (the committed production
  `evaluation_report.json` already contains the recorded per-image held-out rows);
- model `.joblib` binaries (the production bundle is the authoritative copy);
- segmentation review panels and the near-duplicate contact sheet (large images).

## Provenance

- Dataset version: `ds-cc74ed659044`
- Dataset checksum: `cc74ed659044a56034d02e96a9da47679a1164dfdc1ac7a3a980ff16964c7f79`
- Split protocol: `v1`, seed `42`, 96 development / 24 held-out (8 per class)
- Feature set: `1.0.0`, 50 features
- Segmentation / quality configs: `seg-v2` / `quality-v1`
- Selected model: `svm` (RBF SVC, `C=1.0`, `gamma=scale`, `class_weight=balanced`)
- Recorded held-out result (restated, never recomputed): n=24, macro F1
  `0.7854636591478696`, accuracy `0.7916666666666666`

The held-out result was **not** re-evaluated during recovery. The held-out source
run was restored from the already committed production `evaluation_report.json`;
its per-image rows are copies of the recorded rows, not new predictions.

## Regenerate

Dataset summaries, from the repository root:

```powershell
python scripts/audit_dataset.py
python scripts/find_near_duplicates.py
python scripts/run_segmentation_audit.py --no-panels --no-curated
python scripts/build_feature_matrix.py
```

Development training run and the M4 report, from `backend/`:

```powershell
cd backend
# development-only: the 24 held-out rows are never read, fitted or predicted
python -m app.ml.training --development-only
python -m app.ml.evaluation
cd ..
```

`run_training` writes a new timestamped directory such as
`data/processed/training_runs/run_<UTC>_svm/`. `app.ml.evaluation` reads the
canonical development run `run_20261107T175000Z_svm`, so copy the freshly
generated `model_comparison.json`, `model_comparison.md`, `cv_predictions.csv`
and `development_winner_pipeline.joblib` into that canonical directory before
running the evaluation step.

The held-out source run `run_20261107T173626Z_svm` is **not** regenerated. It is
restored by copying the recorded `held_out` block and `held_out_predictions`
rows from the committed
`backend/app/artifacts/production/evaluation_report.json`, because the held-out
set was evaluated exactly once and must not be predicted again.

Then refresh these snapshots by copying the corresponding working artifacts.
Do not edit a snapshot by hand; regenerate it instead.
