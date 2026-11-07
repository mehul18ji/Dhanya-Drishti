"""Tests for the Phase 3 M3 model comparison (no raw dataset required).

The four contract points of M3 are pinned here:

1. only the 96 development rows are used for model selection, and every CV and grid
   search replays the frozen manifest folds (`cv_fold` 0–4) — no splitter is generated;
2. imputation lives inside the scikit-learn pipeline and is fitted per training fold;
3. exactly SVM / Random Forest / KNN are compared, with the required metrics;
4. the held-out rows can never influence selection (poisoning their labels changes
   nothing about the CV results or the winner).
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from sklearn.impute import SimpleImputer
from sklearn.model_selection import PredefinedSplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ml import training as training_module  # noqa: E402
from app.ml.training import (  # noqa: E402
    CLASS_LABELS,
    METRIC_KEYS,
    MODEL_NAMES,
    FeatureMatrix,
    TrainingDataError,
    build_pipeline,
    cross_validate_models,
    evaluate_held_out,
    fit_final_model,
    frozen_fold_cv,
    load_feature_matrix,
    select_winner,
)
from app.vision.config import load_quality_config, load_segmentation_config  # noqa: E402
from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    feature_schema,
)

N_DEVELOPMENT = 96
N_HELD_OUT = 24

#: One-value grids keep the tests fast; the training run uses the real grids.
FAST_GRIDS = {
    "svm": {"model__C": (1.0,)},
    "random_forest": {"model__max_depth": (8,)},
    "knn": {"model__n_neighbors": (5,)},
}

LESION_INDEX = tuple(FEATURE_NAMES.index(name) for name in LESION_DEPENDENT_FEATURES)


def _matrix(*, seed: int = 7) -> FeatureMatrix:
    """A valid 96/24 synthetic matrix with NaN lesion values on some dev rows."""
    rng = np.random.default_rng(seed)
    total = N_DEVELOPMENT + N_HELD_OUT
    X = rng.normal(size=(total, len(FEATURE_NAMES)))

    for row in range(0, N_DEVELOPMENT, 17):
        X[row, list(LESION_INDEX)] = np.nan

    development_labels = [CLASS_LABELS[index % len(CLASS_LABELS)] for index in range(N_DEVELOPMENT)]
    held_out_labels = [CLASS_LABELS[index % len(CLASS_LABELS)] for index in range(N_HELD_OUT)]
    labels = development_labels + held_out_labels

    splits = np.asarray(
        ["development"] * N_DEVELOPMENT + ["held_out_test"] * N_HELD_OUT, dtype=object
    )
    folds = np.asarray([index % 5 for index in range(N_DEVELOPMENT)] + [-1] * N_HELD_OUT)
    return FeatureMatrix(
        X=X,
        y=np.asarray(labels, dtype=object),
        split=splits,
        fold=folds,
        image_ids=tuple(f"img_{index:03d}" for index in range(total)),
        status=("clean",) * total,
        lesion_reliable=np.asarray([not np.isnan(row).any() for row in X]),
        missing_features=tuple(
            LESION_DEPENDENT_FEATURES if np.isnan(row).any() else () for row in X
        ),
        report={
            "feature_set_version": FEATURE_SET_VERSION,
            "schema": feature_schema(),
            "provenance": {"split_version": "v1", "seed": 42},
        },
        matrix_dir=REPO_ROOT / "data" / "processed" / "features" / "feature_set_v1.0.0",
    )


def test_pipelines_impute_inside_and_scale_only_where_it_belongs() -> None:
    for name in MODEL_NAMES:
        pipeline = build_pipeline(name)
        assert pipeline.steps[0][0] == "imputer", f"{name} must impute first"
        imputer = pipeline.named_steps["imputer"]
        assert isinstance(imputer, SimpleImputer)
        assert imputer.add_indicator is True, "missingness indicators are required"
        assert imputer.strategy == "median"
        assert ("scaler" in pipeline.named_steps) == (name in {"svm", "knn"})


def test_imputation_is_fitted_on_the_training_fold_only() -> None:
    """Statistics must come from the fold's training rows, never the whole matrix."""
    # The training block sits at 1.0, the (much larger) held-out block at 100.0,
    # so a median fitted on the pooled matrix would be 100.0, not 1.0.
    train = np.full((8, len(FEATURE_NAMES)), 1.0)
    held = np.full((32, len(FEATURE_NAMES)), 100.0)
    train[:3, 0] = np.nan
    pooled_median = np.nanmedian(np.vstack([train, held])[:, 0])
    train_median = np.nanmedian(train[:, 0])
    assert train_median == pytest.approx(1.0)
    assert pooled_median == pytest.approx(100.0)

    pipeline = build_pipeline("knn")
    pipeline.fit(train, np.asarray([CLASS_LABELS[i % 3] for i in range(len(train))], dtype=object))
    statistics = pipeline.named_steps["imputer"].statistics_
    statistics = np.asarray(statistics, dtype=np.float64)

    assert statistics[0] == pytest.approx(train_median)
    assert statistics[0] != pytest.approx(pooled_median)
    # The held-out block was never seen when the statistics were computed.
    assert statistics[1] == pytest.approx(1.0)


def test_exactly_three_models_are_compared_with_required_metrics() -> None:
    matrix = _matrix()
    comparison = cross_validate_models(matrix, param_grids=FAST_GRIDS, log=lambda _: None)

    assert set(comparison) == set(MODEL_NAMES)
    for name in MODEL_NAMES:
        block = comparison[name]
        assert block["used_held_out_rows"] is False
        assert block["rows_used"] == N_DEVELOPMENT
        assert [fold["fold"] for fold in block["folds"]] == [0, 1, 2, 3, 4]
        assert sum(fold["n_validation"] for fold in block["folds"]) == N_DEVELOPMENT
        for fold in block["folds"]:
            assert "PredefinedSplit" in fold["inner_cv"]
            assert fold["inner_validation_folds"] == [
                other for other in range(5) if other != fold["fold"]
            ]
        for key in METRIC_KEYS:
            assert key in block["out_of_fold"]["metrics"]
            assert key in block["cv"]
            assert 0.0 <= block["cv"][key]["mean"] <= 1.0
        confusion = np.asarray(block["out_of_fold"]["confusion_matrix"])
        assert confusion.shape == (len(CLASS_LABELS), len(CLASS_LABELS))
        assert set(block["out_of_fold"]["per_class"]) == set(CLASS_LABELS)
        assert len(block["predictions"]) == N_DEVELOPMENT


def test_held_out_labels_cannot_influence_selection() -> None:
    clean = _matrix()
    poisoned_labels = list(clean.y)
    for index, split in enumerate(clean.split):
        if split == "held_out_test":
            poisoned_labels[index] = CLASS_LABELS[0]  # deliberately wrong everywhere
    poisoned = replace(clean, y=np.asarray(poisoned_labels, dtype=object))

    assert list(poisoned.y[:N_DEVELOPMENT]) == list(clean.y[:N_DEVELOPMENT])

    baseline = cross_validate_models(clean, param_grids=FAST_GRIDS, log=lambda _: None)
    perturbed = cross_validate_models(poisoned, param_grids=FAST_GRIDS, log=lambda _: None)

    assert select_winner(baseline) == select_winner(perturbed)
    for name in MODEL_NAMES:
        assert baseline[name]["cv"]["macro_f1"]["mean"] == pytest.approx(
            perturbed[name]["cv"]["macro_f1"]["mean"]
        )
        assert baseline[name]["predictions"] == perturbed[name]["predictions"]


def test_winner_selection_uses_mean_cv_macro_f1() -> None:
    comparison = {
        "svm": {"cv": {"macro_f1": {"mean": 0.80, "std": 0.02}}},
        "random_forest": {"cv": {"macro_f1": {"mean": 0.90, "std": 0.05}}},
        "knn": {"cv": {"macro_f1": {"mean": 0.90, "std": 0.01}}},
    }
    # Highest mean wins; the tie on 0.90 breaks on the lower standard deviation.
    assert select_winner(comparison) == "knn"


def test_held_out_evaluation_is_final_and_uses_all_24_rows() -> None:
    matrix = _matrix()
    pipeline, info = fit_final_model(matrix, "knn", param_grid=FAST_GRIDS["knn"])
    assert "frozen manifest folds" in info["inner_cv"]
    assert info["n_training_rows"] == N_DEVELOPMENT

    result = evaluate_held_out(matrix, pipeline)

    assert result["final"] is True
    assert result["used_for_selection"] is False
    assert result["n"] == N_HELD_OUT
    assert len(result["predictions"]) == N_HELD_OUT
    for key in METRIC_KEYS:
        assert 0.0 <= result["metrics"][key] <= 1.0


# --------------------------------------------------------------------------- #
# Loader validation (matrix files written to tmp_path; no raw images)
# --------------------------------------------------------------------------- #

MATRIX_HEADER = (
    "image_id",
    "relative_path",
    "label",
    "split",
    "cv_fold",
    "status",
    "lesion_reliable",
    "lesion_area_percentage",
    "segmentation_config_version",
    "segmentation_config_sha256",
    "quality_config_version",
    "quality_config_sha256",
) + FEATURE_NAMES + ("warnings", "rejections", "missing_features")


def _write_matrix_dir(directory: Path, *, duplicate_development_id: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (REPO_ROOT / "data" / "splits" / "split_manifest.json").read_text(encoding="utf-8")
    )
    segmentation = load_segmentation_config()
    quality = load_quality_config()

    matrix = _matrix(seed=11)
    rows = []
    for index, image_id in enumerate(matrix.image_ids):
        split = str(matrix.split[index])
        fold = int(matrix.fold[index])
        label = str(matrix.y[index])
        record = {
            "image_id": image_id,
            "relative_path": f"data/raw/rice_leaf_diseases/{label}/{image_id}.jpg",
            "label": label,
            "split": split,
            "cv_fold": "" if fold < 0 else str(fold),
            "status": "clean",
            "lesion_reliable": "True",
            "lesion_area_percentage": "4.2",
            "segmentation_config_version": segmentation.segmentation_config_version,
            "segmentation_config_sha256": segmentation.content_sha256,
            "quality_config_version": quality.quality_config_version,
            "quality_config_sha256": quality.content_sha256,
            "warnings": "",
            "rejections": "",
            "missing_features": "",
        }
        for column_index, name in enumerate(FEATURE_NAMES):
            value = float(matrix.X[index, column_index])
            record[name] = "NaN" if np.isnan(value) else f"{value:.6f}"
        rows.append(record)

    if duplicate_development_id:
        # An image that is held out reappearing as development: split violation.
        rows[0]["image_id"] = rows[-1]["image_id"]

    with (directory / "feature_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MATRIX_HEADER))
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "feature_set_version": FEATURE_SET_VERSION,
        "schema": feature_schema(),
        "matrix_columns": list(MATRIX_HEADER),
        "row_count": len(rows),
        "scope": "full",
        "provenance": {
            "dataset_version": manifest["dataset_version"],
            "split_version": manifest["split_version"],
            "seed": manifest["seed"],
        },
        "segmentation_config_version": segmentation.segmentation_config_version,
        "segmentation_config_sha256": segmentation.content_sha256,
        "quality_config_version": quality.quality_config_version,
        "quality_config_sha256": quality.content_sha256,
    }
    (directory / "feature_matrix.json").write_text(json.dumps(report), encoding="utf-8")
    return directory


def test_loader_accepts_the_frozen_matrix_shape(tmp_path: Path) -> None:
    matrix = load_feature_matrix(_write_matrix_dir(tmp_path / "matrix"))

    assert matrix.X.shape == (N_DEVELOPMENT + N_HELD_OUT, len(FEATURE_NAMES))
    assert int((matrix.split == "development").sum()) == N_DEVELOPMENT
    assert int((matrix.split == "held_out_test").sum()) == N_HELD_OUT
    assert np.isnan(matrix.X).any(), "NaN must survive loading"
    assert matrix.development().X.shape[0] == N_DEVELOPMENT
    assert matrix.held_out().X.shape[0] == N_HELD_OUT


def test_loader_rejects_a_split_violation(tmp_path: Path) -> None:
    directory = _write_matrix_dir(tmp_path / "broken", duplicate_development_id=True)
    with pytest.raises(TrainingDataError):
        load_feature_matrix(directory)


# --------------------------------------------------------------------------- #
# The frozen manifest folds are the only splitter
# --------------------------------------------------------------------------- #


def test_frozen_fold_cv_replays_manifest_folds_and_refuses_bad_vectors() -> None:
    fold_vector = np.asarray([index % 5 for index in range(20)], dtype=np.int64)
    cv = frozen_fold_cv(fold_vector)
    assert isinstance(cv, PredefinedSplit)

    splits = list(cv.split(np.zeros((len(fold_vector), 3))))
    assert len(splits) == 5
    for train_index, validation_index in splits:
        folds_in_validation = set(fold_vector[validation_index].tolist())
        assert len(folds_in_validation) == 1
        fold = folds_in_validation.pop()
        assert set(train_index.tolist()) == set(
            np.flatnonzero(fold_vector != fold).tolist()
        )

    # A single frozen fold cannot be turned into a cross-validation.
    with pytest.raises(TrainingDataError):
        frozen_fold_cv(np.zeros(3, dtype=np.int64))
    # Rows without a development fold id (held-out -1) must never reach a search.
    with pytest.raises(TrainingDataError):
        frozen_fold_cv(np.asarray([0, 1, -1], dtype=np.int64))


def test_no_generated_splitter_exists_in_the_training_module() -> None:
    source = Path(training_module.__file__).read_text(encoding="utf-8")
    assert "StratifiedKFold" not in source
    assert "KFold(" not in source
    assert "PredefinedSplit" in source


def _spy_on_grid_search(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record the ``cv`` object of every GridSearchCV the module builds."""
    captured: list = []
    real = training_module.GridSearchCV

    def spy(estimator, param_grid, scoring, cv, **kwargs):
        captured.append(cv)
        return real(estimator, param_grid=param_grid, scoring=scoring, cv=cv, **kwargs)

    monkeypatch.setattr(training_module, "GridSearchCV", spy)
    return captured


def test_inner_search_is_built_from_the_frozen_folds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every search in every model and outer fold validates on frozen folds only."""
    captured = _spy_on_grid_search(monkeypatch)

    cross_validate_models(_matrix(seed=5), param_grids=FAST_GRIDS, log=lambda _: None)

    assert len(captured) == len(MODEL_NAMES) * 5  # one search per model per outer fold
    for cv in captured:
        assert isinstance(cv, PredefinedSplit)
        held_out_folds = set(np.asarray(cv.test_fold).tolist())
        assert len(held_out_folds) == 4
        assert held_out_folds <= {0, 1, 2, 3, 4}

    # The search spent on outer fold 0 excludes fold 0's rows entirely.
    assert set(np.asarray(captured[0].test_fold).tolist()) == {1, 2, 3, 4}


def test_final_fit_searches_on_all_five_frozen_folds(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _spy_on_grid_search(monkeypatch)

    fit_final_model(_matrix(seed=5), "svm", param_grid=FAST_GRIDS["svm"])

    assert len(captured) == 1
    assert set(np.asarray(captured[0].test_fold).tolist()) == {0, 1, 2, 3, 4}
