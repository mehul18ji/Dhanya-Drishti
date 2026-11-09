# Demo images

These four files are for **UI demonstration only**. They are not a new training set,
not a new evaluation set, and not a held-out benchmark. Nothing here was used to fit,
tune, calibrate or re-evaluate the production model (`svm-v1.0.0`).

> **Important:** a training or development image that the model classifies correctly is
> **not evidence of generalization**. Generalization is reported only by the single frozen
> 24-image held-out evaluation recorded in the model manifest and evaluation report
> (macro F1 `0.7855`, accuracy `0.7917`). That evaluation was consumed once and was not
> rerun to produce this folder.

No smartphone images were available for this project, so none are included here. No
smartphone result is claimed anywhere in this folder or in the project reports.

## Contents

| File | Source | Split status | Expected dataset label / behaviour | Intended use |
|---|---|---|---|---|
| `01.jpg` | Approved Kaggle Rice Leaf Diseases dataset: `data/raw/rice_leaf_diseases/Bacterial leaf blight/DSC_0365.JPG` | Development (not one of the 24 held-out images) | Bacterial Leaf Blight | Dashboard upload → predicted or uncertain result for UI demonstration |
| `02.jpg` | Approved Kaggle Rice Leaf Diseases dataset: `data/raw/rice_leaf_diseases/Brown spot/DSC_0105.jpg` | Development (not one of the 24 held-out images) | Brown Spot | Dashboard upload → predicted or uncertain result for UI demonstration |
| `03.jpg` | Approved Kaggle Rice Leaf Diseases dataset: `data/raw/rice_leaf_diseases/Leaf smut/DSC_0513.jpg` | Development (not one of the 24 held-out images) | Leaf Smut | Dashboard upload → predicted or uncertain result for UI demonstration |
| `04_rejected_example.png` | Synthetic blank frame generated with the same construction as `blank_bytes()` in `scripts/run_local_acceptance.py` (640×640 near-white PNG) | Not a dataset image | HTTP 200 `status: "rejected"`, reason `NO_CLEAR_LEAF_FOUND`; no disease label, no severity, no prediction id, no history row | Dashboard upload → rejected-state demonstration |

## Per-file notes

### `01.jpg`

- **Source:** `data/raw/rice_leaf_diseases/Bacterial leaf blight/DSC_0365.JPG` from the
  approved 120-image dataset. Copied byte-for-byte; only the demo filename changed.
- **Expected supported label:** Bacterial Leaf Blight.
- **UI-only:** yes. This is a development image. A correct result on it demonstrates the
  interface and pipeline, not generalization. It must never be cited as a held-out or
  field-performance result.

### `02.jpg`

- **Source:** `data/raw/rice_leaf_diseases/Brown spot/DSC_0105.jpg` from the approved
  120-image dataset. Copied byte-for-byte; only the demo filename changed.
- **Expected supported label:** Brown Spot.
- **UI-only:** yes. Same warning as above: a training/development image is not evidence
  of generalization.### `03.jpg`

- **Source:** `data/raw/rice_leaf_diseases/Leaf smut/DSC_0513.jpg` from the approved 120-image dataset. Copied byte-for-byte; only the demo filename changed. This image is in the development split (its `cv_fold` entry is in `data/splits/cv_folds.json`) and is **not** one of the 24 held-out images.
- **Expected supported label:** Leaf Smut.
- **UI-only:** yes. Same warning as above: a training/development image is not evidence
  of generalization.

### `04_rejected_example.png`

- **Source:** synthetic 640×640 near-white blank PNG, generated with the same parameters
  as the local-acceptance rejection input (`Image.new("RGB", (640, 640), (250, 250, 248))`).
  It is not a photograph and is not part of the approved dataset.
- **Expected behaviour:** the backend returns HTTP 200 with `status: "rejected"`,
  `reason_code: "NO_CLEAR_LEAF_FOUND"`, no `prediction_id`, no artifacts, no disease label
  and no severity. The dashboard shows the rejected state, and the image does not appear
  in history.
- **UI-only:** yes. It demonstrates the rejection path; it is not an evaluation sample.

## Usage

The three dataset samples are also bundled with the dashboard as byte-identical copies in
`frontend/public/demo/` (`demo-image-1.jpg`, `demo-image-2.jpg`, `demo-image-3.jpg`, in the
table order above). The Analysis page lists them as **Demo Image 1/2/3** under **Or try a
demo leaf**, so a visitor can run the whole flow without the dataset, the repository or a
local file. Their public names are deliberately neutral: the selected file name appears in
the preview, the result card and the history table, so it must not reveal the expected
label. The mapping to the dataset source stays in this file, and those three copies must
stay byte-identical to the files in this folder.

Upload these files through the running dashboard (`frontend` + `backend`) exactly as a
user would. Do not use them in automated metric calculations or notebooks. The canonical
evaluation evidence remains:

- `backend/app/artifacts/production/evaluation_report.json`
- `data/processed/reproducibility/evaluation_report.json`
- `docs/LOCAL_ACCEPTANCE_REPORT.md`

## Reproducibility warning

The three dataset images come from the development split. The model was trained on that
split, so high accuracy on these images is expected and proves nothing about unseen or
field photographs. The only reported generalization figure is the frozen held-out result
above; it was not recomputed for this demo folder.
