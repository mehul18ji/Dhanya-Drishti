"""Export the approved Phase 3 model bundle (Phase 3 M5).

Writes the canonical deployable bundle that Phase 4 will load, into::

    backend/app/artifacts/production/
        model_pipeline.joblib     fitted imputer -> scaler -> SVC pipeline
        preprocessing.json        fitted imputer/scaler parameters (inspectable)
        feature_schema.json       feature set v1.0.0, 50 ordered names
        segmentation_config.json  seg-v2 / quality-v1 versions + SHA-256
        evaluation_report.json    the Phase 3 M4 report, copied verbatim
        model_manifest.json       model, metrics, provenance, artifact hashes

This script **never trains, tunes or fits anything**. It loads the already-selected
pipeline from the corrected development-only run and copies the frozen artifacts, so
re-running it cannot change the approved model.

Usage (from the repository root)::

    python scripts/export_artifacts.py
    python scripts/export_artifacts.py --output-dir tmp/bundle   # dry check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import joblib  # noqa: E402
import numpy as np  # noqa: E402

from app.vision.config import (  # noqa: E402
    load_quality_config,
    load_segmentation_config,
)
from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    feature_schema,
)

TRAINING_RUN_ROOT = REPO_ROOT / "data" / "processed" / "training_runs"
EVALUATION_REPORT_PATH = TRAINING_RUN_ROOT / "evaluation" / "evaluation_report.json"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "app" / "artifacts" / "production"

#: Corrected development-only M3 run (frozen manifest folds). Authoritative source.
SOURCE_RUN = "run_20261107T175000Z_svm"
SOURCE_MODEL_FILE = "development_winner_pipeline.joblib"
#: Pre-correction run that consumed the held-out rows; used only to prove the
#: exported estimator is the one whose held-out result we report.
REFERENCE_RUN = "run_20261107T173626Z_svm"
REFERENCE_MODEL_FILE = "winner_pipeline.joblib"

CLASS_LABELS: tuple[str, ...] = (
    "bacterial_leaf_blight",
    "brown_spot",
    "leaf_smut",
)
EXPECTED_FEATURE_COUNT = 50
EXPECTED_DEVELOPMENT_ROWS = 96
BUNDLE_VERSION = "1.0.0"

MODEL_FILE = "model_pipeline.joblib"
PREPROCESSING_FILE = "preprocessing.json"
SCHEMA_FILE = "feature_schema.json"
CONFIG_FILE = "segmentation_config.json"
EVALUATION_FILE = "evaluation_report.json"
MANIFEST_FILE = "model_manifest.json"

BUNDLE_FILES: tuple[str, ...] = (
    MODEL_FILE,
    PREPROCESSING_FILE,
    SCHEMA_FILE,
    CONFIG_FILE,
    EVALUATION_FILE,
    MANIFEST_FILE,
)

KNOWN_FAILURE_CASES: tuple[str, ...] = (
    "A faint lesion band can survive on the dark lower edge of some Bacterial Leaf "
    "Blight strips; the border exclusion reduces it but does not remove it.",
    "Segmentation thresholds are calibrated on white-paper studio photographs; noisy "
    "or cluttered phone backgrounds are untested.",
    "There is no healthy-leaf class: the model always returns one of the three "
    "diseases and must not be presented as a diseased/healthy test.",
    "Images whose lesion stage reports no healthy-green reference yield NaN lesion "
    "and spatial features; those values must stay missing (never 0.0) and must be "
    "imputed within a training fold only.",
    "The dataset is 120 visually similar images, so scores are optimistic and the "
    "single 24-image held-out result carries roughly +/-0.05-0.08 macro-F1 noise.",
)


class ExportError(RuntimeError):
    """The frozen artifacts are not the approved bundle inputs."""


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON with LF endings on every platform.

    ``Path.write_text`` translates ``\\n`` to the platform line separator, which
    emits CRLF on Windows. A bundle whose manifest records CRLF hashes then fails
    integrity verification on a Linux host (or after ``core.autocrlf`` strips
    CRLF on commit), because the recorded hash no longer matches the file. Writing
    encoded bytes guarantees byte-identical LF output on Windows and Linux.
    """
    Path(path).write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))


def _source_paths(
    *, training_run_root: Path | None = None
) -> tuple[Path, Path, Path]:
    root = Path(training_run_root) if training_run_root is not None else TRAINING_RUN_ROOT
    model = root / SOURCE_RUN / SOURCE_MODEL_FILE
    reference = root / REFERENCE_RUN / REFERENCE_MODEL_FILE
    comparison = root / REFERENCE_RUN / "model_comparison.json"
    return model, reference, comparison


def load_selected_pipeline(
    *,
    training_run_root: Path | None = None,
    log=print,
) -> tuple[Any, dict[str, Any]]:
    """Load the approved SVM pipeline and verify it is the expected estimator.

    Nothing is fitted here: the object is read from disk exactly as M3 saved it.
    """
    model_path, reference_path, comparison_path = _source_paths(
        training_run_root=training_run_root
    )
    if not model_path.exists():
        raise ExportError(f"missing selected pipeline: {model_path}")

    pipeline = joblib.load(model_path)
    steps = [name for name, _ in pipeline.steps]
    if steps != ["imputer", "scaler", "model"]:
        raise ExportError(f"unexpected pipeline steps {steps}, expected imputer/scaler/model")

    estimator = pipeline.named_steps["model"]
    if type(estimator).__name__ != "SVC":
        raise ExportError(f"selected estimator is {type(estimator).__name__}, expected SVC")
    if estimator.kernel != "rbf":
        raise ExportError(f"selected estimator kernel is {estimator.kernel!r}, expected 'rbf'")

    classes = [str(label) for label in pipeline.classes_]
    if tuple(classes) != CLASS_LABELS:
        raise ExportError(f"pipeline classes {classes} != {list(CLASS_LABELS)}")
    if int(pipeline.n_features_in_) != EXPECTED_FEATURE_COUNT:
        raise ExportError(
            f"pipeline expects {pipeline.n_features_in_} features, expected "
            f"{EXPECTED_FEATURE_COUNT}"
        )

    imputer = pipeline.named_steps["imputer"]
    statistics = np.asarray(imputer.statistics_, dtype=np.float64)
    if statistics.shape != (EXPECTED_FEATURE_COUNT,):
        raise ExportError(f"imputer statistics have shape {statistics.shape}")

    info: dict[str, Any] = {
        "source_run": SOURCE_RUN,
        "source_file": SOURCE_MODEL_FILE,
        "source_sha256": sha256_of(model_path),
        "hyperparameters": {
            key: value
            for key, value in estimator.get_params().items()
            if key in {"C", "gamma", "kernel", "class_weight", "random_state"}
        },
        "identical_to_reference_pipeline": None,
    }

    if reference_path.exists():
        reference = joblib.load(reference_path)
        comparisons = {
            "imputer_statistics": np.array_equal(
                statistics,
                np.asarray(reference.named_steps["imputer"].statistics_, dtype=np.float64),
            ),
            "scaler_mean": np.array_equal(
                np.asarray(pipeline.named_steps["scaler"].mean_, dtype=np.float64),
                np.asarray(reference.named_steps["scaler"].mean_, dtype=np.float64),
            ),
            "scaler_scale": np.array_equal(
                np.asarray(pipeline.named_steps["scaler"].scale_, dtype=np.float64),
                np.asarray(reference.named_steps["scaler"].scale_, dtype=np.float64),
            ),
            "support_vectors": np.array_equal(
                np.asarray(estimator.support_vectors_, dtype=np.float64),
                np.asarray(reference.named_steps["model"].support_vectors_, dtype=np.float64),
            ),
            "dual_coef": np.array_equal(
                np.asarray(estimator.dual_coef_, dtype=np.float64),
                np.asarray(reference.named_steps["model"].dual_coef_, dtype=np.float64),
            ),
            "intercept": np.array_equal(
                np.asarray(estimator.intercept_, dtype=np.float64),
                np.asarray(reference.named_steps["model"].intercept_, dtype=np.float64),
            ),
        }
        info["identical_to_reference_pipeline"] = all(comparisons.values())
        info["reference_comparison"] = comparisons
        if not all(comparisons.values()):
            raise ExportError(
                "the exported pipeline is not the estimator whose held-out result is "
                f"reported: {comparisons}"
            )
        log(f"  verified identical to {REFERENCE_RUN} (held-out result applies)")

    spec = {}
    if comparison_path.exists():
        payload = json.loads(comparison_path.read_text(encoding="utf-8"))
        spec["held_out"] = payload.get("held_out")
    info["held_out_source"] = spec.get("held_out")
    return pipeline, info


def build_preprocessing(pipeline: Any) -> dict[str, Any]:
    """Snapshot the fitted imputer/scaler so the bundle is inspectable."""
    imputer = pipeline.named_steps["imputer"]
    scaler = pipeline.named_steps["scaler"]
    indicator = getattr(imputer, "indicator_", None)
    indicator_features = (
        [int(index) for index in getattr(indicator, "features_", [])] if indicator else []
    )
    return {
        "pipeline_steps": [name for name, _ in pipeline.steps],
        "imputer": {
            "class": type(imputer).__name__,
            "strategy": imputer.strategy,
            "add_indicator": bool(imputer.add_indicator),
            "indicator_features": indicator_features,
            "statistics": [
                {"feature": name, "median": float(imputer.statistics_[index])}
                for index, name in enumerate(FEATURE_NAMES)
            ],
        },
        "scaler": {
            "class": type(scaler).__name__,
            "mean": [float(value) for value in scaler.mean_],
            "scale": [float(value) for value in scaler.scale_],
        },
        "nan_policy": (
            "Median imputation and missingness indicators are steps inside the fitted "
            "pipeline, so their statistics come from the development rows. An "
            "uncalibrated lesion value is NaN on input and is never turned into 0.0 "
            "before imputation."
        ),
        "inference_contract": (
            "Pass one float64 row of the 50 schema-ordered features, NaN allowed for "
            "lesion/spatial features; the pipeline imputes, scales and predicts."
        ),
    }


def build_manifest(
    pipeline: Any,
    info: dict[str, Any],
    *,
    output_dir: Path,
    evaluation_report: dict[str, Any],
    exported_at: str,
) -> dict[str, Any]:
    segmentation = load_segmentation_config()
    quality = load_quality_config()
    estimator = pipeline.named_steps["model"]
    development = evaluation_report.get("development") or {}
    models = development.get("models") or {}
    svm_block = models.get("svm") or {}
    cv = svm_block.get("cv") or {}
    held_out = info.get("held_out_source") or {}

    artifacts = {}
    for name in BUNDLE_FILES:
        path = Path(output_dir) / name
        if path.exists() and name != MANIFEST_FILE:
            artifacts[name] = {
                "sha256": sha256_of(path),
                "bytes": int(path.stat().st_size),
            }

    provenance = evaluation_report.get("provenance") or {}
    return {
        "bundle_version": BUNDLE_VERSION,
        "bundle_status": "approved_phase3_m5_export",
        "exported_at": exported_at,
        "model": {
            "name": "svm",
            "estimator": f"SVC(kernel={estimator.kernel!r}, class_weight='balanced')",
            "hyperparameters": info["hyperparameters"],
            "classes": list(CLASS_LABELS),
            "calibrated_probabilities": False,
            "confidence_note": (
                "The pipeline exposes decision_function, not calibrated probabilities "
                "(scikit-learn 1.9 deprecates SVC(probability=True)). Confidence "
                "handling is a Phase 4 decision and must not claim probabilities."
            ),
        },
        "features": {
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_count": EXPECTED_FEATURE_COUNT,
            "schema_file": SCHEMA_FILE,
            "lesion_dependent_features": list(LESION_DEPENDENT_FEATURES),
            "input_shape": "one row of 50 float64 values in schema order; NaN allowed",
        },
        "preprocessing": {
            "file": PREPROCESSING_FILE,
            "steps": ["imputer (median + missingness indicators)", "scaler (StandardScaler)"],
            "fitted_on": "the 96 development rows (fold-local during selection)",
        },
        "training": {
            "run": info["source_run"],
            "source_file": info["source_file"],
            "source_sha256": info["source_sha256"],
            "development_rows": EXPECTED_DEVELOPMENT_ROWS,
            "selection_metric": "cv_macro_f1_mean",
            "cv_protocol": (
                "frozen manifest folds cv_fold 0-4 replayed with PredefinedSplit; no "
                "generated splitter"
            ),
            "cv": {
                "macro_f1_mean": cv.get("macro_f1", {}).get("mean"),
                "macro_f1_std": cv.get("macro_f1", {}).get("std"),
                "accuracy_mean": cv.get("accuracy", {}).get("mean"),
                "balanced_accuracy_mean": cv.get("balanced_accuracy", {}).get("mean"),
            },
        },
        "evaluation": {
            "file": EVALUATION_FILE,
            "cv_macro_f1_mean": cv.get("macro_f1", {}).get("mean"),
            "cv_macro_f1_std": cv.get("macro_f1", {}).get("std"),
            "out_of_fold_macro_f1": (svm_block.get("out_of_fold") or {})
            .get("metrics", {})
            .get("macro_f1"),
            "held_out": {
                "n": held_out.get("n"),
                "metrics": held_out.get("metrics"),
                "status": "evaluated_once_after_selection_not_recomputed",
            },
        },
        "provenance": {
            "dataset_version": provenance.get("dataset_version"),
            "dataset_checksum_sha256": provenance.get("dataset_checksum_sha256"),
            "split_protocol": provenance.get("split_version"),
            "seed": provenance.get("seed"),
            "segmentation_config_version": segmentation.segmentation_config_version,
            "segmentation_config_sha256": segmentation.content_sha256,
            "quality_config_version": quality.quality_config_version,
            "quality_config_sha256": quality.content_sha256,
        },
        "environment": {
            "python": sys.version.split()[0],
            "scikit_learn": _module_version("sklearn"),
            "numpy": _module_version("numpy"),
            "joblib": _module_version("joblib"),
        },
        "reproducibility": {
            "produced_by": "scripts/export_artifacts.py",
            "retrained_during_export": False,
            "identical_to_reference_pipeline": info["identical_to_reference_pipeline"],
            "reference_run": REFERENCE_RUN,
        },
        "artifacts": artifacts,
        "known_failure_cases": list(KNOWN_FAILURE_CASES),
        "severity_disclaimer": (
            "Severity is an experimental estimate from lesion area and may not reflect "
            "the actual severity of the disease."
        ),
    }


def _module_version(name: str) -> str:
    module = sys.modules.get(name)
    if module is None:
        try:
            module = __import__(name)
        except Exception:  # pragma: no cover - optional metadata
            return "unknown"
    return str(getattr(module, "__version__", "unknown"))


def export_bundle(
    *,
    output_dir: Path | None = None,
    training_run_root: Path | None = None,
    evaluation_report_path: Path | None = None,
    log=print,
) -> dict[str, Any]:
    """Write the production bundle and return the manifest."""
    destination = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    evaluation_source = (
        Path(evaluation_report_path)
        if evaluation_report_path is not None
        else EVALUATION_REPORT_PATH
    )
    if not evaluation_source.exists():
        raise ExportError(
            f"missing M4 evaluation report: {evaluation_source}; run "
            "`python -m app.ml.evaluation` first"
        )

    pipeline, info = load_selected_pipeline(training_run_root=training_run_root, log=log)
    evaluation_report = json.loads(evaluation_source.read_text(encoding="utf-8"))

    destination.mkdir(parents=True, exist_ok=True)
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    joblib.dump(pipeline, destination / MODEL_FILE)
    _write_json(destination / PREPROCESSING_FILE, build_preprocessing(pipeline))

    schema = feature_schema()
    schema["classes"] = list(CLASS_LABELS)
    segmentation = load_segmentation_config()
    quality = load_quality_config()
    schema["segmentation_config_version"] = segmentation.segmentation_config_version
    schema["segmentation_config_sha256"] = segmentation.content_sha256
    schema["quality_config_version"] = quality.quality_config_version
    schema["quality_config_sha256"] = quality.content_sha256
    _write_json(destination / SCHEMA_FILE, schema)

    _write_json(
        destination / CONFIG_FILE,
        {
            "segmentation_config_version": segmentation.segmentation_config_version,
            "segmentation_config_sha256": segmentation.content_sha256,
            "quality_config_version": quality.quality_config_version,
            "quality_config_sha256": quality.content_sha256,
            "segmentation_source": "backend/configs/segmentation.yaml",
            "quality_source": "backend/configs/quality_thresholds.yaml",
            "note": (
                "The bundle pins the Phase 2 configurations that produced the "
                "features; a different hash means the features are not comparable."
            ),
        },
    )

    # The M4 evaluation report is an authoritative input; copy it verbatim except
    # for line endings so the bundle stays LF-consistent (see ``_write_json``).
    evaluation_bytes = evaluation_source.read_bytes()
    if b"\r\n" in evaluation_bytes:
        evaluation_bytes = evaluation_bytes.replace(b"\r\n", b"\n")
    (destination / EVALUATION_FILE).write_bytes(evaluation_bytes)

    manifest = build_manifest(
        pipeline,
        info,
        output_dir=destination,
        evaluation_report=evaluation_report,
        exported_at=exported_at,
    )
    _write_json(destination / MANIFEST_FILE, manifest)
    log(f"bundle written to {destination}")
    for name in BUNDLE_FILES:
        log(f"  {name}")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=None, help="override the bundle directory")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        manifest = export_bundle(
            output_dir=Path(args.output_dir) if args.output_dir else None
        )
    except ExportError as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1

    model = manifest["model"]
    cv = manifest["training"]["cv"]
    held_out = manifest["evaluation"]["held_out"]
    print()
    print(f"model            : {model['name']} {model['estimator']}")
    print(f"hyperparameters  : {model['hyperparameters']}")
    print(f"features         : v{manifest['features']['feature_set_version']} "
          f"({manifest['features']['feature_count']})")
    print(f"CV macro F1      : {cv['macro_f1_mean']:.4f} +/- {cv['macro_f1_std']:.4f}")
    print(f"held-out (n={held_out['n']}): macro F1 "
          f"{held_out['metrics']['macro_f1']:.4f} (restated, not recomputed)")
    print(f"identical to reference pipeline: "
          f"{manifest['reproducibility']['identical_to_reference_pipeline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
