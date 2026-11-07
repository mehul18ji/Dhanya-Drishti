"""Local classical-model training and comparison (Phase 3 M3).

Compares **exactly** three candidates on the frozen ``feature_set_v1.0.0`` matrix:

- ``svm`` — median imputation + missingness indicators + ``StandardScaler`` + RBF SVM
- ``random_forest`` — the same imputation, no scaling, ``RandomForestClassifier``
- ``knn`` — the same imputation + ``StandardScaler`` + ``KNeighborsClassifier``

Discipline enforced here (PRD §10, decisions P-10 / P-13, split protocol v1):

- Model selection and hyperparameter tuning use **only** the 96 development rows,
  with the fixed five folds from ``data/splits/cv_folds.json``. No splitter is ever
  generated: every CV and every ``GridSearchCV`` runs on :func:`frozen_fold_cv`, a
  ``PredefinedSplit`` that replays those exact ``cv_fold`` ids. Inside outer fold
  *k* the inner search validates on the remaining four frozen folds, so a row is
  never re-shuffled into an invented partition.
- Imputation (and its missingness indicators) is a **step inside each
  scikit-learn pipeline**, so it is fitted on the training fold only. NaN is
  never replaced by ``0.0`` in the matrix itself and no row is dropped.
- The winner is chosen by **mean cross-validated macro F1**. Only then is it
  refit on all 96 development rows and evaluated on the 24 held-out test images,
  exactly once. That test result is final and is never used to tune anything —
  the code path makes the ordering structural: :func:`cross_validate_models` and
  :func:`select_winner` never see a held-out row.
- Nothing here is imported by the API and nothing trains inside a request.

Outputs go to a git-ignored training-run directory, never to
``backend/app/artifacts/production/`` (production packaging is a later step).
"""

from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:  # pragma: no cover - import-time convenience
    sys.path.insert(0, str(BACKEND_DIR))

from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GridSearchCV, PredefinedSplit  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.svm import SVC  # noqa: E402

from app.vision.config import load_quality_config, load_segmentation_config  # noqa: E402
from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
)

FEATURE_MATRIX_ROOT = REPO_ROOT / "data" / "processed" / "features"
TRAINING_RUN_ROOT = REPO_ROOT / "data" / "processed" / "training_runs"
SPLIT_MANIFEST_PATH = REPO_ROOT / "data" / "splits" / "split_manifest.json"

SEED = 42
MODEL_NAMES: tuple[str, ...] = ("svm", "random_forest", "knn")
CLASS_LABELS: tuple[str, ...] = (
    "bacterial_leaf_blight",
    "brown_spot",
    "leaf_smut",
)
SPLIT_DEVELOPMENT = "development"
SPLIT_TEST = "held_out_test"
EXPECTED_DEVELOPMENT_ROWS = 96
EXPECTED_HELD_OUT_ROWS = 24
EXPECTED_TEST_PER_CLASS = 8
EXPECTED_SPLIT_VERSION = "v1"
EXPECTED_FOLDS = (0, 1, 2, 3, 4)

METRIC_KEYS: tuple[str, ...] = (
    "accuracy",
    "balanced_accuracy",
    "macro_precision",
    "macro_recall",
    "macro_f1",
)

REQUIRED_STATE_COLUMNS: tuple[str, ...] = (
    "image_id",
    "relative_path",
    "label",
    "split",
    "cv_fold",
    "status",
    "lesion_reliable",
)

#: Small, deliberately honest grids: hyperparameters are searched *inside* each
#: development fold, never against the held-out test images.
DEFAULT_PARAM_GRIDS: dict[str, dict[str, Sequence[Any]]] = {
    "svm": {"model__C": (1.0, 10.0), "model__gamma": ("scale",)},
    "random_forest": {"model__max_depth": (None, 8)},
    "knn": {"model__n_neighbors": (3, 5, 7)},
}


class TrainingDataError(ValueError):
    """The feature matrix is not the frozen, validated matrix this module expects."""


# --------------------------------------------------------------------------- #
# The frozen folds — the only splitter this module is allowed to use
# --------------------------------------------------------------------------- #


def frozen_fold_cv(fold_ids: Sequence[int] | np.ndarray) -> PredefinedSplit:
    """Replay the frozen manifest fold ids; never generate a new split.

    ``test_fold`` is the per-row ``cv_fold`` value taken verbatim from the frozen
    feature matrix (which itself comes from ``data/splits/cv_folds.json``), so
    scikit-learn validates each fold exactly as the manifest defines it. Rows with
    ``-1`` would always be training rows, and are rejected here because only
    development rows may be passed in.
    """
    folds = np.asarray(fold_ids, dtype=np.int64)
    if folds.ndim != 1 or folds.size == 0:
        raise TrainingDataError("frozen_fold_cv needs a non-empty 1-D fold vector")
    if np.any(folds < 0):
        raise TrainingDataError(
            "frozen_fold_cv received rows without a development fold id"
        )
    distinct = sorted({int(value) for value in folds})
    if len(distinct) < 2:
        raise TrainingDataError(
            "frozen_fold_cv needs at least two frozen folds, got "
            f"{distinct}"
        )
    return PredefinedSplit(test_fold=folds)


# --------------------------------------------------------------------------- #
# Matrix loading and validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FeatureMatrix:
    """Validated feature matrix with split and fold membership kept explicit."""

    X: np.ndarray
    y: np.ndarray
    split: np.ndarray
    fold: np.ndarray
    image_ids: tuple[str, ...]
    status: tuple[str, ...]
    lesion_reliable: np.ndarray
    missing_features: tuple[tuple[str, ...], ...]
    report: dict
    matrix_dir: Path

    @property
    def feature_names(self) -> tuple[str, ...]:
        return FEATURE_NAMES

    @property
    def provenance(self) -> dict:
        return dict(self.report.get("provenance", {}))

    def development(self) -> "FeatureMatrix":
        """The 96 rows allowed for model selection."""
        return self._subset(self.split == SPLIT_DEVELOPMENT)

    def held_out(self) -> "FeatureMatrix":
        """The 24 rows reserved for the single final evaluation."""
        return self._subset(self.split == SPLIT_TEST)

    def _subset(self, mask: np.ndarray) -> "FeatureMatrix":
        return FeatureMatrix(
            X=self.X[mask],
            y=self.y[mask],
            split=self.split[mask],
            fold=self.fold[mask],
            image_ids=tuple(np.asarray(self.image_ids, dtype=object)[mask]),
            status=tuple(np.asarray(self.status, dtype=object)[mask]),
            lesion_reliable=self.lesion_reliable[mask],
            missing_features=tuple(
                np.asarray(self.missing_features, dtype=object)[mask].tolist()
            ),
            report=self.report,
            matrix_dir=self.matrix_dir,
        )


def default_matrix_dir(feature_set_version: str = FEATURE_SET_VERSION) -> Path:
    return FEATURE_MATRIX_ROOT / f"feature_set_v{feature_set_version}"


def _parse_float(raw: str, *, image_id: str, column: str) -> float:
    text = (raw or "").strip()
    if text in {"", "NaN", "nan", "NA"}:
        return float("nan")
    try:
        value = float(text)
    except ValueError as exc:  # pragma: no cover - defensive
        raise TrainingDataError(
            f"{image_id}: column {column!r} is not numeric ({raw!r})"
        ) from exc
    if math.isinf(value):
        raise TrainingDataError(f"{image_id}: column {column!r} is infinite")
    return value


def _split_manifest() -> dict:
    if not SPLIT_MANIFEST_PATH.exists():  # pragma: no cover - repository invariant
        raise TrainingDataError(f"missing {SPLIT_MANIFEST_PATH}")
    return json.loads(SPLIT_MANIFEST_PATH.read_text(encoding="utf-8"))


def validate_matrix_report(
    report: Mapping[str, Any],
    *,
    feature_names: Sequence[str] = FEATURE_NAMES,
    verify_configs: bool = True,
) -> None:
    """Reject a matrix that is not the frozen schema/split/config combination."""
    version = report.get("feature_set_version")
    if version != FEATURE_SET_VERSION:
        raise TrainingDataError(
            f"feature_set_version {version!r} does not match the active "
            f"{FEATURE_SET_VERSION!r}"
        )

    schema = report.get("schema") or {}
    schema_names = tuple(schema.get("feature_names") or ())
    if schema_names != tuple(feature_names):
        raise TrainingDataError("matrix schema feature order does not match the extractor")

    columns = list(report.get("matrix_columns") or ())
    for required in REQUIRED_STATE_COLUMNS:
        if required not in columns:
            raise TrainingDataError(f"matrix is missing required column {required!r}")
    present = [column for column in columns if column in set(feature_names)]
    if tuple(present) != tuple(feature_names):
        raise TrainingDataError(
            "matrix feature columns are missing or out of schema order"
        )

    split_protocol = report.get("provenance") or {}
    manifest = _split_manifest()
    if split_protocol.get("split_version") != EXPECTED_SPLIT_VERSION:
        raise TrainingDataError(
            f"split_version {split_protocol.get('split_version')!r} is not the frozen "
            f"{EXPECTED_SPLIT_VERSION!r}"
        )
    if manifest.get("split_version") != EXPECTED_SPLIT_VERSION:
        raise TrainingDataError("split manifest no longer declares split protocol v1")
    for key in ("dataset_version", "seed"):
        if split_protocol.get(key) != manifest.get(key):
            raise TrainingDataError(
                f"matrix {key} {split_protocol.get(key)!r} does not match the split "
                f"manifest ({manifest.get(key)!r})"
            )

    if verify_configs:
        segmentation = load_segmentation_config()
        quality = load_quality_config()
        checks = (
            ("segmentation_config_version", segmentation.segmentation_config_version),
            ("segmentation_config_sha256", segmentation.content_sha256),
            ("quality_config_version", quality.quality_config_version),
            ("quality_config_sha256", quality.content_sha256),
        )
        for key, expected in checks:
            if report.get(key) != expected:
                raise TrainingDataError(
                    f"matrix {key} {report.get(key)!r} does not match the active "
                    f"configuration ({expected!r}); rebuild the matrix"
                )


def validate_matrix_rows(matrix: FeatureMatrix) -> None:
    """Reject a matrix whose splits, folds or labels violate split protocol v1."""
    if matrix.X.shape[1] != len(FEATURE_NAMES):
        raise TrainingDataError(
            f"expected {len(FEATURE_NAMES)} feature columns, got {matrix.X.shape[1]}"
        )
    if len(set(matrix.image_ids)) != len(matrix.image_ids):
        raise TrainingDataError("duplicate image_id in the matrix")

    unknown_split = set(matrix.split) - {SPLIT_DEVELOPMENT, SPLIT_TEST}
    if unknown_split:
        raise TrainingDataError(f"unexpected split values: {sorted(unknown_split)}")

    unknown_label = set(matrix.y) - set(CLASS_LABELS)
    if unknown_label:
        raise TrainingDataError(f"unexpected disease labels: {sorted(unknown_label)}")

    development_mask = matrix.split == SPLIT_DEVELOPMENT
    test_mask = matrix.split == SPLIT_TEST
    if int(development_mask.sum()) != EXPECTED_DEVELOPMENT_ROWS:
        raise TrainingDataError(
            f"expected {EXPECTED_DEVELOPMENT_ROWS} development rows, got "
            f"{int(development_mask.sum())}"
        )
    if int(test_mask.sum()) != EXPECTED_HELD_OUT_ROWS:
        raise TrainingDataError(
            f"expected {EXPECTED_HELD_OUT_ROWS} held-out rows, got {int(test_mask.sum())}"
        )

    test_ids = set(np.asarray(matrix.image_ids, dtype=object)[test_mask])
    development_ids = set(np.asarray(matrix.image_ids, dtype=object)[development_mask])
    if test_ids & development_ids:
        raise TrainingDataError("an image is present in both development and held-out rows")

    held_out_counts = {
        label: int((matrix.y[test_mask] == label).sum()) for label in CLASS_LABELS
    }
    if set(held_out_counts.values()) != {EXPECTED_TEST_PER_CLASS}:
        raise TrainingDataError(
            f"held-out rows must be {EXPECTED_TEST_PER_CLASS} per class, got "
            f"{held_out_counts}"
        )

    development_folds = set(matrix.fold[development_mask].tolist())
    if development_folds - set(EXPECTED_FOLDS):
        raise TrainingDataError(
            f"unexpected development fold ids: {sorted(development_folds)}"
        )
    if len(development_folds) != len(EXPECTED_FOLDS):
        raise TrainingDataError(
            f"expected all {len(EXPECTED_FOLDS)} development folds, got "
            f"{sorted(development_folds)}"
        )
    if not np.all(matrix.fold[test_mask] == -1):
        raise TrainingDataError("held-out rows must not carry a development fold id")


def load_feature_matrix(
    matrix_dir: Path | None = None,
    *,
    verify_configs: bool = True,
) -> FeatureMatrix:
    """Load and validate the frozen feature matrix. NaN is preserved verbatim."""
    directory = Path(matrix_dir) if matrix_dir is not None else default_matrix_dir()
    csv_path = directory / "feature_matrix.csv"
    json_path = directory / "feature_matrix.json"
    if not csv_path.exists() or not json_path.exists():
        raise TrainingDataError(
            f"feature matrix not found in {directory}; run "
            "`python scripts/build_feature_matrix.py` first"
        )

    report = json.loads(json_path.read_text(encoding="utf-8"))
    validate_matrix_report(report, verify_configs=verify_configs)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or ())
        records = list(reader)

    missing_columns = [name for name in FEATURE_NAMES if name not in header]
    if missing_columns:
        raise TrainingDataError(
            f"feature matrix is missing schema columns: {missing_columns[:5]}"
        )
    missing_columns = [name for name in REQUIRED_STATE_COLUMNS if name not in header]
    if missing_columns:
        raise TrainingDataError(f"feature matrix is missing columns: {missing_columns}")

    rows = len(records)
    if report.get("row_count") is not None and int(report["row_count"]) != rows:
        raise TrainingDataError(
            f"report claims {report['row_count']} rows but the CSV has {rows}"
        )

    X = np.empty((rows, len(FEATURE_NAMES)), dtype=np.float64)
    labels: list[str] = []
    splits: list[str] = []
    folds: list[int] = []
    image_ids: list[str] = []
    statuses: list[str] = []
    reliable: list[bool] = []
    missing: list[tuple[str, ...]] = []

    for row_index, record in enumerate(records):
        image_id = record["image_id"]
        for column_index, name in enumerate(FEATURE_NAMES):
            X[row_index, column_index] = _parse_float(
                record[name], image_id=image_id, column=name
            )
        labels.append(record["label"])
        splits.append(record["split"])
        raw_fold = (record.get("cv_fold") or "").strip()
        folds.append(int(raw_fold) if raw_fold else -1)
        image_ids.append(image_id)
        statuses.append(record["status"])
        reliable.append(record["lesion_reliable"].strip().lower() == "true")
        missing.append(
            tuple(part for part in (record.get("missing_features") or "").split("|") if part)
        )

    matrix = FeatureMatrix(
        X=X,
        y=np.asarray(labels, dtype=object),
        split=np.asarray(splits, dtype=object),
        fold=np.asarray(folds, dtype=np.int64),
        image_ids=tuple(image_ids),
        status=tuple(statuses),
        lesion_reliable=np.asarray(reliable, dtype=bool),
        missing_features=tuple(missing),
        report=report,
        matrix_dir=directory,
    )
    validate_matrix_rows(matrix)
    return matrix


# --------------------------------------------------------------------------- #
# Pipelines
# --------------------------------------------------------------------------- #


def _imputer() -> SimpleImputer:
    """Median imputation + missingness indicators, fitted inside the pipeline.

    ``add_indicator=True`` appends a binary indicator per column that had missing
    values in the *training* data, so "lesion could not be measured" stays visible
    to the model instead of being disguised as a low lesion area (decision P-13).
    """
    return SimpleImputer(
        strategy="median", add_indicator=True, keep_empty_features=True
    )


def build_pipeline(model_name: str) -> Pipeline:
    """Build one candidate pipeline with scaling only where it belongs."""
    if model_name == "svm":
        return Pipeline(
            [
                ("imputer", _imputer()),
                ("scaler", StandardScaler()),
                # Probability calibration is deliberately *not* enabled here:
                # scikit-learn 1.9 deprecates ``SVC(probability=True)`` in favour of
                # ``CalibratedClassifierCV``, and calibrated probabilities are a
                # Phase 4 decision, not a model-selection one.
                (
                    "model",
                    SVC(kernel="rbf", class_weight="balanced", random_state=SEED),
                ),
            ]
        )
    if model_name == "random_forest":
        return Pipeline(
            [
                ("imputer", _imputer()),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=400,
                        random_state=SEED,
                        class_weight="balanced_subsample",
                        n_jobs=1,
                    ),
                ),
            ]
        )
    if model_name == "knn":
        return Pipeline(
            [
                ("imputer", _imputer()),
                ("scaler", StandardScaler()),
                ("model", KNeighborsClassifier(weights="distance")),
            ]
        )
    raise ValueError(f"unknown model {model_name!r}; expected one of {MODEL_NAMES}")


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Accuracy, balanced accuracy, macro P/R/F1, confusion matrix, per-class table."""
    labels = list(CLASS_LABELS)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        },
        "labels": labels,
        "n": int(len(y_true)),
    }


def _mean_std(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()) if array.size else float("nan"),
        "std": float(array.std(ddof=0)) if array.size else float("nan"),
        "min": float(array.min()) if array.size else float("nan"),
        "max": float(array.max()) if array.size else float("nan"),
    }


# --------------------------------------------------------------------------- #
# Cross-validation on development rows only
# --------------------------------------------------------------------------- #


def cross_validate_models(
    matrix: FeatureMatrix,
    *,
    param_grids: Mapping[str, Mapping[str, Sequence[Any]]] | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, dict]:
    """Nested CV over the 96 development rows; held-out rows are never touched."""
    development = matrix.development()
    grids = dict(param_grids or DEFAULT_PARAM_GRIDS)
    folds = sorted(EXPECTED_FOLDS)

    results: dict[str, dict] = {}
    for model_name in MODEL_NAMES:
        if model_name not in grids:
            raise ValueError(f"missing parameter grid for {model_name!r}")

        fold_records: list[dict] = []
        oof_true: list[str] = []
        oof_pred: list[str] = []
        oof_ids: list[str] = []

        for fold in folds:
            train_mask = development.fold != fold
            valid_mask = development.fold == fold
            X_train, y_train = development.X[train_mask], development.y[train_mask]
            X_valid, y_valid = development.X[valid_mask], development.y[valid_mask]
            if len(X_valid) == 0:  # pragma: no cover - validated earlier
                raise TrainingDataError(f"fold {fold} is empty")

            # The inner search must replay the frozen folds too: inside outer
            # fold k it validates on the remaining four manifest folds, never on
            # a freshly generated partition.
            inner_folds = sorted({int(value) for value in development.fold[train_mask]})
            search = GridSearchCV(
                build_pipeline(model_name),
                param_grid=dict(grids[model_name]),
                scoring="f1_macro",
                cv=frozen_fold_cv(development.fold[train_mask]),
                refit=True,
                n_jobs=1,
                error_score="raise",
            )
            search.fit(X_train, y_train)
            predictions = search.predict(X_valid)

            fold_metrics = compute_metrics(y_valid, predictions)
            fold_records.append(
                {
                    "fold": int(fold),
                    "n_train": int(len(X_train)),
                    "n_validation": int(len(X_valid)),
                    "inner_cv": "PredefinedSplit over the remaining frozen manifest folds",
                    "inner_validation_folds": [value for value in inner_folds if value != int(fold)],
                    "best_params": {
                        key: (value if isinstance(value, (int, float, str, bool)) or value is None
                              else str(value))
                        for key, value in search.best_params_.items()
                    },
                    "inner_best_macro_f1": float(search.best_score_),
                    "metrics": {key: fold_metrics[key] for key in METRIC_KEYS},
                }
            )
            oof_true.extend(y_valid.tolist())
            oof_pred.extend(list(predictions))
            oof_ids.extend(
                np.asarray(development.image_ids, dtype=object)[valid_mask].tolist()
            )
            log(
                f"  {model_name:<14} fold {fold}: macro F1 "
                f"{fold_metrics['macro_f1']:.4f} "
                f"(n_train={len(X_train)}, n_val={len(X_valid)})"
            )

        pooled = compute_metrics(np.asarray(oof_true), np.asarray(oof_pred))
        cv_variation = {
            key: _mean_std([record["metrics"][key] for record in fold_records])
            for key in METRIC_KEYS
        }
        results[model_name] = {
            "model": model_name,
            "folds": fold_records,
            "cv": cv_variation,
            "cv_macro_f1_mean": cv_variation["macro_f1"]["mean"],
            "cv_macro_f1_std": cv_variation["macro_f1"]["std"],
            "out_of_fold": {
                "metrics": {key: pooled[key] for key in METRIC_KEYS},
                "confusion_matrix": pooled["confusion_matrix"],
                "per_class": pooled["per_class"],
                "labels": pooled["labels"],
                "n": pooled["n"],
            },
            "predictions": [
                {"image_id": image_id, "y_true": truth, "y_pred": prediction}
                for image_id, truth, prediction in zip(oof_ids, oof_true, oof_pred)
            ],
            "rows_used": int(len(oof_true)),
            "used_held_out_rows": False,
        }
    return results


def select_winner(comparison: Mapping[str, dict]) -> str:
    """Pick by mean CV macro F1; ties break on lower std, then fixed name order."""
    missing = [name for name in MODEL_NAMES if name not in comparison]
    if missing:
        raise ValueError(f"comparison is missing models: {missing}")
    return min(
        MODEL_NAMES,
        key=lambda name: (
            -float(comparison[name]["cv"]["macro_f1"]["mean"]),
            float(comparison[name]["cv"]["macro_f1"]["std"]),
            MODEL_NAMES.index(name),
        ),
    )


# --------------------------------------------------------------------------- #
# Final: refit on all development rows, evaluate held-out once
# --------------------------------------------------------------------------- #


def fit_final_model(
    matrix: FeatureMatrix,
    model_name: str,
    *,
    param_grid: Mapping[str, Sequence[Any]] | None = None,
) -> tuple[Pipeline, dict[str, Any]]:
    """Tune on the 96 development rows (frozen folds) and refit on all of them."""
    development = matrix.development()
    grid = dict(param_grid or DEFAULT_PARAM_GRIDS[model_name])
    search = GridSearchCV(
        build_pipeline(model_name),
        param_grid=grid,
        scoring="f1_macro",
        cv=frozen_fold_cv(development.fold),
        refit=True,
        n_jobs=1,
        error_score="raise",
    )
    search.fit(development.X, development.y)
    pipeline = search.best_estimator_
    info = {
        "best_params": {
            key: (value if isinstance(value, (int, float, str, bool)) or value is None else str(value))
            for key, value in search.best_params_.items()
        },
        "inner_best_macro_f1": float(search.best_score_),
        "inner_cv": "PredefinedSplit over the five frozen manifest folds",
        "n_training_rows": int(len(development.y)),
        "feature_names": list(FEATURE_NAMES),
        "feature_set_version": FEATURE_SET_VERSION,
    }
    return pipeline, info


def evaluate_held_out(
    matrix: FeatureMatrix,
    pipeline: Pipeline,
) -> dict[str, Any]:
    """The one and only held-out evaluation. Never fed back into selection."""
    held_out = matrix.held_out()
    predictions = pipeline.predict(held_out.X)
    metrics = compute_metrics(held_out.y, predictions)
    return {
        "final": True,
        "used_for_selection": False,
        "n": metrics["n"],
        "metrics": {key: metrics[key] for key in METRIC_KEYS},
        "confusion_matrix": metrics["confusion_matrix"],
        "per_class": metrics["per_class"],
        "labels": metrics["labels"],
        "predictions": [
            {"image_id": image_id, "y_true": truth, "y_pred": prediction}
            for image_id, truth, prediction in zip(
                held_out.image_ids, held_out.y.tolist(), predictions.tolist()
            )
        ],
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def _decimals(value: float, places: int = 4) -> str:
    return f"{value:.{places}f}" if math.isfinite(value) else "n/a"


def _render_held_out_section(report: Mapping[str, Any]) -> list[str]:
    """Held-out block: restated once, or explicitly marked as not re-run."""
    held_out = report.get("held_out")
    lines: list[str] = ["## Held-out evaluation (once, after selection)", ""]
    if held_out is None:
        lines.append(
            "**Not run in this report.** This is a development-only run: the 24 held-out "
            "rows were not read, fitted on or predicted. The single held-out evaluation "
            "recorded earlier is restated in `PROJECT_STATUS.md` and is not recomputed."
        )
        lines.append("")
        return lines

    class_labels = list(held_out["labels"])
    lines.append(
        "| accuracy | balanced acc. | macro precision | macro recall | macro F1 | n |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| {_decimals(held_out['metrics']['accuracy'])} | "
        f"{_decimals(held_out['metrics']['balanced_accuracy'])} | "
        f"{_decimals(held_out['metrics']['macro_precision'])} | "
        f"{_decimals(held_out['metrics']['macro_recall'])} | "
        f"{_decimals(held_out['metrics']['macro_f1'])} | {held_out['n']} |"
    )
    lines.append("")
    lines.append("| true \\ predicted | " + " | ".join(class_labels) + " |")
    lines.append("|---|" + "---:|" * len(class_labels))
    for row_index, label in enumerate(class_labels):
        cells = [
            str(held_out["confusion_matrix"][row_index][col])
            for col in range(len(class_labels))
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def render_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Model comparison — feature set v{report['feature_set_version']}")
    lines.append("")
    lines.append(
        f"Generated `{report['generated_at']}` | seed {report['seed']} | "
        f"development rows {report['development_rows']} | held-out rows {report['held_out_rows']}"
    )
    lines.append("")
    lines.append(
        "Selection metric: **mean cross-validated macro F1** on the 96 development rows, "
        "cross-validated and grid-searched only on the frozen manifest folds "
        "(`cv_fold` 0–4, replayed with `PredefinedSplit`). No splitter is generated."
    )
    lines.append("")
    lines.append("## Cross-validation (development rows only)")
    lines.append("")
    lines.append("| model | accuracy | balanced acc. | macro precision | macro recall | macro F1 | macro F1 std |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for name in MODEL_NAMES:
        cv = report["comparison"][name]["cv"]
        lines.append(
            f"| {name} | {_decimals(cv['accuracy']['mean'])} | "
            f"{_decimals(cv['balanced_accuracy']['mean'])} | "
            f"{_decimals(cv['macro_precision']['mean'])} | "
            f"{_decimals(cv['macro_recall']['mean'])} | "
            f"{_decimals(cv['macro_f1']['mean'])} | {_decimals(cv['macro_f1']['std'])} |"
        )
    lines.append("")
    lines.append("## Out-of-fold confusion matrices")
    lines.append("")
    labels = report["comparison"][MODEL_NAMES[0]]["out_of_fold"]["labels"]
    for name in MODEL_NAMES:
        block = report["comparison"][name]["out_of_fold"]
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| true \\ predicted | " + " | ".join(labels) + " |")
        lines.append("|---|" + "---:|" * len(labels))
        for row_index, label in enumerate(labels):
            cells = [str(block["confusion_matrix"][row_index][col]) for col in range(len(labels))]
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("Per-class:")
        lines.append("")
        lines.append("| class | precision | recall | F1 | support |")
        lines.append("|---|---:|---:|---:|---:|")
        for label in labels:
            per = block["per_class"][label]
            lines.append(
                f"| {label} | {_decimals(per['precision'])} | {_decimals(per['recall'])} | "
                f"{_decimals(per['f1'])} | {per['support']} |"
            )
        lines.append("")
    lines.append("## Selected model")
    lines.append("")
    winner = report["winner"]
    lines.append(
        f"**{winner['model']}** chosen by mean CV macro F1 "
        f"({_decimals(winner['cv_macro_f1_mean'])} ± {_decimals(winner['cv_macro_f1_std'])}). "
        f"Final hyperparameters: `{json.dumps(winner['best_params'])}`."
    )
    lines.append("")
    lines.extend(_render_held_out_section(report))
    lines.append("## Caveats")
    lines.append("")
    lines.append(report["caveat"])
    lines.append("")
    return "\n".join(lines)


CAVEAT = (
    "Scores come from 96 development rows and 24 held-out rows of one small, "
    "visually similar 3-class dataset with no healthy class. They are optimistically "
    "biased by dataset size and near-duplicate similarity and are **not** a "
    "real-world accuracy claim. Severe/uncertain handling is a Phase 4 concern; "
    "nothing here is validated on field photographs."
)


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


def _write_predictions(
    path: Path,
    predictions: Sequence[dict],
    *,
    fieldnames: Sequence[str] = ("image_id", "y_true", "y_pred"),
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(predictions)


def run_training(
    matrix_dir: Path | None = None,
    *,
    output_root: Path | None = None,
    param_grids: Mapping[str, Mapping[str, Sequence[Any]]] | None = None,
    save_model: bool = True,
    development_only: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run the comparison on the frozen folds.

    With ``development_only=True`` the 24 held-out rows are never read, fitted on
    or predicted — used by corrections that must not consume the held-out set a
    second time. Otherwise the winner is evaluated on them exactly once.
    """
    matrix = load_feature_matrix(matrix_dir)
    grids = dict(param_grids or DEFAULT_PARAM_GRIDS)

    development = matrix.development()
    held_out_count = int((matrix.split == SPLIT_TEST).sum())
    log(f"feature matrix    : {matrix.matrix_dir}")
    log(f"schema            : v{matrix.report['feature_set_version']} "
        f"({len(FEATURE_NAMES)} features)")
    log(f"dataset / split   : {matrix.provenance.get('dataset_version')} / "
        f"{matrix.provenance.get('split_version')} (seed {matrix.provenance.get('seed')})")
    log(f"development rows  : {len(development.y)} (model selection only)")
    log(
        f"held-out rows     : {held_out_count} "
        f"({'not touched — development-only run' if development_only else 'single final evaluation'})"
    )
    log("")

    comparison = cross_validate_models(matrix, param_grids=grids, log=log)
    winner_name = select_winner(comparison)
    log("")
    for name in MODEL_NAMES:
        cv = comparison[name]["cv"]["macro_f1"]
        log(f"  {name:<14} CV macro F1 {cv['mean']:.4f} ± {cv['std']:.4f}")
    log(f"  selected      : {winner_name}")
    log("")

    pipeline, final_info = fit_final_model(
        matrix, winner_name, param_grid=grids[winner_name]
    )
    if development_only:
        held_out_result = None
        log("")
        log("held-out        : NOT evaluated — development-only run; the 24 test rows")
        log("                  were not read, fitted on or predicted")
    else:
        held_out_result = evaluate_held_out(matrix, pipeline)
        log(
            f"held-out (once) : macro F1 {held_out_result['metrics']['macro_f1']:.4f} | "
            f"accuracy {held_out_result['metrics']['accuracy']:.4f}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(output_root or TRAINING_RUN_ROOT) / f"run_{stamp}_{winner_name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "feature_set_version": matrix.report["feature_set_version"],
        "matrix_dir": str(matrix.matrix_dir),
        "matrix_report_columns": matrix.report.get("matrix_columns"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": int(matrix.provenance.get("seed") or SEED),
        "cv_protocol": {
            "outer": "frozen manifest folds cv_fold 0-4 (PredefinedSplit)",
            "inner": "remaining frozen manifest folds (PredefinedSplit) per outer fold",
            "generated_splitter": False,
        },
        "held_out_status": (
            "not_evaluated_development_only"
            if development_only
            else "evaluated_once_after_selection"
        ),
        "development_rows": int(len(development.y)),
        "held_out_rows": held_out_count,
        "provenance": matrix.provenance,
        "segmentation_config_version": matrix.report.get("segmentation_config_version"),
        "segmentation_config_sha256": matrix.report.get("segmentation_config_sha256"),
        "quality_config_version": matrix.report.get("quality_config_version"),
        "quality_config_sha256": matrix.report.get("quality_config_sha256"),
        "missing_values_by_group": matrix.report.get("missing_values_by_group"),
        "nan_policy": matrix.report.get("nan_policy"),
        "comparison": {
            name: {key: value for key, value in comparison[name].items() if key != "predictions"}
            for name in MODEL_NAMES
        },
        "winner": {
            "model": winner_name,
            "selection_metric": "cv_macro_f1_mean",
            "cv_macro_f1_mean": comparison[winner_name]["cv"]["macro_f1"]["mean"],
            "cv_macro_f1_std": comparison[winner_name]["cv"]["macro_f1"]["std"],
            "best_params": final_info["best_params"],
            "inner_best_macro_f1": final_info["inner_best_macro_f1"],
            "n_training_rows": final_info["n_training_rows"],
        },
        "held_out": (
            None
            if held_out_result is None
            else {
                key: value
                for key, value in held_out_result.items()
                if key != "predictions"
            }
        ),
        "caveat": CAVEAT,
        "artifacts": {
            "comparison_json": "model_comparison.json",
            "comparison_markdown": "model_comparison.md",
            "cv_predictions_csv": "cv_predictions.csv",
            "held_out_predictions_csv": (
                None if development_only else "held_out_predictions.csv"
            ),
            "model_joblib": (
                None
                if not save_model
                else (
                    "development_winner_pipeline.joblib"
                    if development_only
                    else "winner_pipeline.joblib"
                )
            ),
        },
    }

    (run_dir / "model_comparison.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "model_comparison.md").write_text(render_markdown(report), encoding="utf-8")

    cv_rows: list[dict] = []
    for name in MODEL_NAMES:
        for prediction in comparison[name]["predictions"]:
            cv_rows.append(
                {
                    "model": name,
                    "image_id": prediction["image_id"],
                    "y_true": prediction["y_true"],
                    "y_pred": prediction["y_pred"],
                }
            )
    _write_predictions(
        run_dir / "cv_predictions.csv",
        cv_rows,
        fieldnames=("model", "image_id", "y_true", "y_pred"),
    )
    if held_out_result is not None:
        _write_predictions(
            run_dir / "held_out_predictions.csv", held_out_result["predictions"]
        )

    if save_model:
        import joblib

        model_path = run_dir / (
            "development_winner_pipeline.joblib"
            if development_only
            else "winner_pipeline.joblib"
        )
        joblib.dump(pipeline, model_path)

    report["run_dir"] = str(run_dir)
    log("")
    log(f"run directory  : {run_dir}")
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-dir", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--no-model", action="store_true", help="do not save the joblib")
    parser.add_argument(
        "--development-only",
        action="store_true",
        help="never read or predict the 24 held-out rows (correction runs)",
    )
    args = parser.parse_args(argv)

    run_training(
        Path(args.matrix_dir) if args.matrix_dir else None,
        output_root=Path(args.output_root) if args.output_root else None,
        save_model=not args.no_model,
        development_only=args.development_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
