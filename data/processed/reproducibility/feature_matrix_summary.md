# Feature matrix — feature set v1.0.0

Generated: `2026-11-09T14:43:02+00:00` | scope: **full**
Dataset: `ds-cc74ed659044` | split protocol `v1` (seed 42)

Rows: **120** | columns: 65 (50 schema features)

## Rows per split

| split | images | rows with values | clean | uncertain | rejected | lesion unreliable |
|---|---:|---:|---:|---:|---:|---:|
| development | 96 | 96 | 71 | 25 | 0 | 0 |
| held_out_test | 24 | 24 | 16 | 8 | 0 | 0 |

## Class counts

| split | bacterial_leaf_blight | brown_spot | leaf_smut |
|---|---:|---:|---:|
| development | 32 | 32 | 32 |
| held_out_test | 8 | 8 | 8 |

## Missing values by feature group (NaN cells, never imputed)

| group | features | development | held_out_test |
|---|---:|---:|---:|
| colour | 22 | 0 | 0 |
| texture | 5 | 0 | 0 |
| shape | 8 | 0 | 0 |
| lesion | 6 | 0 | 0 |
| spatial | 9 | 0 | 0 |

## Provenance

- Schema: `dhanyadrishti-leaf-features` v1.0.0 (50 features)
- Segmentation config: `seg-v2` (sha256 `c3784f11df53d13d4db515b1a11b36fd9b1bfbe34777de1d99ad2380a4a1bba1`)
- Quality config: `quality-v1` (sha256 `c4cfe9e2f9110db2b13a021dc43ed860e19bdd33f65d64d3dece1e34ce3e062e`)
- NaN policy: Unreliable lesion/spatial features are real NaN cells (decision P-13) and are never replaced with 0.0; no row is dropped. Imputation, if any, must be fitted per training fold inside the scikit-learn pipeline.
