"""Tests for the Phase 3 M5 production artifact bundle.

These tests never retrain and never touch the raw dataset or the held-out rows:

- they validate the committed bundle against the live feature schema and Phase 2
  configuration hashes;
- they load the bundle in a **separate, clean process** and run one deterministic
  feature row through prediction, asserting the output structure and classes;
- they prove re-exporting produces the same model bytes, so export cannot drift.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.vision.config import (  # noqa: E402
    load_quality_config,
    load_segmentation_config,
    load_severity_config,
)
from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
)

BUNDLE_DIR = REPO_ROOT / "backend" / "app" / "artifacts" / "production"
BUNDLE_FILES = (
    "model_pipeline.joblib",
    "preprocessing.json",
    "feature_schema.json",
    "segmentation_config.json",
    "evaluation_report.json",
    "model_manifest.json",
)
CLASS_LABELS = ("bacterial_leaf_blight", "brown_spot", "leaf_smut")
PRD_SEVERITY_DISCLAIMER = (
    "Severity is an experimental estimate based on the visible lesion area in this image. "
    "It is not a validated agronomic severity grade."
)


def _json(name: str) -> dict:
    return json.loads((BUNDLE_DIR / name).read_text(encoding="utf-8"))


def test_bundle_contains_exactly_the_expected_files() -> None:
    missing = [name for name in BUNDLE_FILES if not (BUNDLE_DIR / name).exists()]
    assert not missing, f"production bundle is incomplete: {missing}"
    present = sorted(
        path.name for path in BUNDLE_DIR.iterdir() if path.name != ".gitkeep"
    )
    assert present == sorted(BUNDLE_FILES), "the bundle holds exactly the documented files"


def test_schema_matches_the_live_extractor_and_configs() -> None:
    schema = _json("feature_schema.json")
    config = _json("segmentation_config.json")
    segmentation = load_segmentation_config()
    quality = load_quality_config()

    assert schema["feature_set_version"] == FEATURE_SET_VERSION
    assert tuple(schema["feature_names"]) == FEATURE_NAMES
    assert schema["feature_count"] == len(FEATURE_NAMES) == 50
    assert tuple(schema["lesion_dependent_features"]) == LESION_DEPENDENT_FEATURES
    assert tuple(schema["classes"]) == CLASS_LABELS

    assert config["segmentation_config_version"] == segmentation.segmentation_config_version
    assert config["segmentation_config_sha256"] == segmentation.content_sha256
    assert config["quality_config_version"] == quality.quality_config_version
    assert config["quality_config_sha256"] == quality.content_sha256


def test_manifest_records_the_approved_model_and_frozen_provenance() -> None:
    from scripts.export_artifacts import sha256_of

    manifest = _json("model_manifest.json")

    assert manifest["model"]["name"] == "svm"
    assert manifest["model"]["hyperparameters"]["C"] == 1.0
    assert manifest["model"]["hyperparameters"]["gamma"] == "scale"
    assert tuple(manifest["model"]["classes"]) == CLASS_LABELS
    assert manifest["model"]["calibrated_probabilities"] is False

    assert manifest["features"]["feature_set_version"] == FEATURE_SET_VERSION
    assert manifest["features"]["feature_count"] == 50
    assert manifest["training"]["development_rows"] == 96
    assert manifest["training"]["selection_metric"] == "cv_macro_f1_mean"
    assert manifest["training"]["cv"]["macro_f1_mean"] == pytest.approx(0.8411814, rel=1e-6)

    held_out = manifest["evaluation"]["held_out"]
    assert held_out["n"] == 24
    assert held_out["metrics"]["macro_f1"] == pytest.approx(0.7854636, rel=1e-6)
    assert held_out["status"] == "evaluated_once_after_selection_not_recomputed"
    # The held-out rows are never embedded in the bundle as per-image records.
    assert "predictions" not in held_out

    provenance = manifest["provenance"]
    assert provenance["split_protocol"] == "v1"
    assert provenance["dataset_version"] == "ds-cc74ed659044"
    assert provenance["segmentation_config_version"] == "seg-v2"
    assert provenance["quality_config_version"] == "quality-v1"

    assert manifest["reproducibility"]["retrained_during_export"] is False
    assert manifest["reproducibility"]["identical_to_reference_pipeline"] is True
    assert manifest["known_failure_cases"], "known failure cases must be documented"
    assert manifest["severity_disclaimer"] == load_severity_config().disclaimer
    assert manifest["severity_disclaimer"] == PRD_SEVERITY_DISCLAIMER

    for name, record in manifest["artifacts"].items():
        path = BUNDLE_DIR / name
        assert path.exists(), f"manifest references a missing artifact: {name}"
        assert record["sha256"] == sha256_of(path), f"{name} does not match its manifest hash"


def _deterministic_row() -> list[float]:
    """A valid, reproducible feature row: the fitted imputer medians."""
    preprocessing = _json("preprocessing.json")
    statistics = preprocessing["imputer"]["statistics"]
    assert [item["feature"] for item in statistics] == list(FEATURE_NAMES)
    row = [float(item["median"]) for item in statistics]
    assert all(np.isfinite(row))
    return row


def test_bundle_predicts_in_a_clean_process_without_training_code(tmp_path: Path) -> None:
    row = _deterministic_row()
    row_path = tmp_path / "row.json"
    row_path.write_text(json.dumps(row), encoding="utf-8")

    script = textwrap.dedent(
        """
        import json
        import os
        import sys

        import joblib
        import numpy as np

        bundle = sys.argv[1]
        row = json.loads(open(sys.argv[2], encoding="utf-8").read())

        pipeline = joblib.load(os.path.join(bundle, "model_pipeline.joblib"))
        prediction = pipeline.predict(np.asarray([row], dtype=np.float64))

        print(json.dumps({
            "prediction": str(prediction[0]),
            "classes": [str(label) for label in pipeline.classes_],
            "n_features": int(pipeline.n_features_in_),
            "output_size": int(np.asarray(prediction).size),
            "app_modules_imported": sorted(
                name for name in sys.modules if name == "app" or name.startswith("app.")
            ),
        }))
        """
    )

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "-c", script, str(BUNDLE_DIR), str(row_path)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),  # a directory where `app` is not importable
        env=environment,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload["n_features"] == 50
    assert payload["output_size"] == 1
    assert tuple(payload["classes"]) == CLASS_LABELS
    assert payload["prediction"] in CLASS_LABELS
    assert payload["app_modules_imported"] == [], (
        "the bundle must be usable without importing application or training code"
    )


def test_re_export_reproduces_the_same_model_bytes(tmp_path: Path) -> None:
    from scripts.export_artifacts import export_bundle, sha256_of

    export_bundle(output_dir=tmp_path, log=lambda _: None)

    committed = sha256_of(BUNDLE_DIR / "model_pipeline.joblib")
    regenerated = sha256_of(tmp_path / "model_pipeline.joblib")
    assert regenerated == committed, "export must copy the approved model, never refit it"

    schema = json.loads((tmp_path / "feature_schema.json").read_text(encoding="utf-8"))
    assert tuple(schema["feature_names"]) == FEATURE_NAMES
    manifest = json.loads((tmp_path / "model_manifest.json").read_text(encoding="utf-8"))
    assert manifest["evaluation"]["held_out"]["n"] == 24
