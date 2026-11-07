"""Tests for the Phase 4 M1 artifact-backed inference service.

Everything here uses the committed bundle and synthetic feature rows. No model is
trained, nothing reads the raw dataset, and the 24 held-out rows are never touched.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services import inference_service as inference  # noqa: E402
from app.services.inference_service import (  # noqa: E402
    SCORE_KIND,
    BundleIntegrityError,
    ConfigMismatchError,
    InferenceService,
    SchemaMismatchError,
    UnusableFeatureVectorError,
    get_inference_service,
    load_bundle,
    reset_inference_service,
)
from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    FeatureExtractionResult,
)

BUNDLE_DIR = REPO_ROOT / "backend" / "app" / "artifacts" / "production"
CLASS_LABELS = ("bacterial_leaf_blight", "brown_spot", "leaf_smut")


@pytest.fixture(autouse=True)
def _clear_service_cache() -> None:
    reset_inference_service()
    yield
    reset_inference_service()


def _bundle_json(name: str) -> dict:
    return json.loads((BUNDLE_DIR / name).read_text(encoding="utf-8"))


def _bundle_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "bundle"
    shutil.copytree(BUNDLE_DIR, destination)
    return destination


def _refresh_manifest_hash(bundle_dir: Path, name: str) -> None:
    """Keep a deliberately edited file consistent with the manifest."""
    manifest = json.loads((bundle_dir / "model_manifest.json").read_text(encoding="utf-8"))
    path = bundle_dir / name
    manifest["artifacts"][name] = {
        "sha256": inference._sha256_of(path),
        "bytes": path.stat().st_size,
    }
    (bundle_dir / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _write_json(bundle_dir: Path, name: str, payload: dict) -> None:
    (bundle_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _median_row() -> list[float]:
    statistics = _bundle_json("preprocessing.json")["imputer"]["statistics"]
    assert [item["feature"] for item in statistics] == list(FEATURE_NAMES)
    return [float(item["median"]) for item in statistics]


def _result(
    values: np.ndarray | None = None,
    *,
    status: str = "clean",
    lesion_reliable: bool = True,
    missing: tuple[str, ...] = (),
    lesion_area_percentage: float | None = 12.5,
    schema_version: str = FEATURE_SET_VERSION,
    segmentation_sha: str | None = None,
    quality_sha: str | None = None,
) -> FeatureExtractionResult:
    config = _bundle_json("segmentation_config.json")
    if values is None and status != "rejected":
        values = np.asarray(_median_row(), dtype=np.float32)
    return FeatureExtractionResult(
        values=values,
        status=status,  # type: ignore[arg-type]
        lesion_reliable=lesion_reliable,
        lesion_reference_available=lesion_reliable,
        lesion_area_percentage=lesion_area_percentage,
        warnings=("SMALL_IMAGE",) if status != "clean" else (),
        rejections=(),
        missing_features=missing,
        schema_version=schema_version,
        segmentation_config_version=config["segmentation_config_version"],
        segmentation_config_sha256=(
            config["segmentation_config_sha256"] if segmentation_sha is None else segmentation_sha
        ),
        quality_config_version=config["quality_config_version"],
        quality_config_sha256=(
            config["quality_config_sha256"] if quality_sha is None else quality_sha
        ),
    )


# --------------------------------------------------------------------------- #
# Loading the committed bundle
# --------------------------------------------------------------------------- #


def test_committed_bundle_loads_with_the_approved_model() -> None:
    bundle = load_bundle()

    assert bundle.model_name == "svm"
    assert bundle.model_version == "svm-v1.0.0"
    assert bundle.classes == CLASS_LABELS
    assert bundle.feature_names == FEATURE_NAMES
    assert bundle.feature_set_version == FEATURE_SET_VERSION
    assert bundle.segmentation_config_version == "seg-v2"
    assert bundle.quality_config_version == "quality-v1"
    assert bundle.produces_probabilities is False, (
        "the bundle must not claim calibrated probabilities"
    )


def test_service_is_loaded_once_per_process() -> None:
    first = get_inference_service()
    second = get_inference_service()

    assert first is second, "startup must load the bundle exactly once"

    reset_inference_service()
    third = get_inference_service()
    assert third is not first, "reset must force a fresh load"


# --------------------------------------------------------------------------- #
# Corrupted / mismatched bundle rejection
# --------------------------------------------------------------------------- #


def test_corrupted_model_file_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    model = bundle_dir / "model_pipeline.joblib"
    model.write_bytes(model.read_bytes()[:512] + b"corrupted")

    with pytest.raises(BundleIntegrityError, match="does not match its manifest hash"):
        load_bundle(bundle_dir)


def test_tampered_metadata_file_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    preprocessing = json.loads(
        (bundle_dir / "preprocessing.json").read_text(encoding="utf-8")
    )
    preprocessing["imputer"]["strategy"] = "mean"  # edited without re-exporting
    _write_json(bundle_dir, "preprocessing.json", preprocessing)

    with pytest.raises(BundleIntegrityError):
        load_bundle(bundle_dir)


def test_missing_artifact_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    (bundle_dir / "evaluation_report.json").unlink()

    with pytest.raises(BundleIntegrityError, match="missing"):
        load_bundle(bundle_dir)


def test_feature_schema_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    schema = json.loads((bundle_dir / "feature_schema.json").read_text(encoding="utf-8"))
    schema["feature_names"] = list(reversed(schema["feature_names"]))
    _write_json(bundle_dir, "feature_schema.json", schema)
    _refresh_manifest_hash(bundle_dir, "feature_schema.json")

    with pytest.raises(SchemaMismatchError, match="feature names/order"):
        load_bundle(bundle_dir)


def test_feature_version_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    schema = json.loads((bundle_dir / "feature_schema.json").read_text(encoding="utf-8"))
    schema["feature_set_version"] = "0.9.0"
    _write_json(bundle_dir, "feature_schema.json", schema)
    _refresh_manifest_hash(bundle_dir, "feature_schema.json")

    with pytest.raises(SchemaMismatchError):
        load_bundle(bundle_dir)


def test_configuration_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    bundle_dir = _bundle_copy(tmp_path)
    config = json.loads((bundle_dir / "segmentation_config.json").read_text(encoding="utf-8"))
    config["segmentation_config_sha256"] = "0" * 64
    _write_json(bundle_dir, "segmentation_config.json", config)
    _refresh_manifest_hash(bundle_dir, "segmentation_config.json")

    with pytest.raises(ConfigMismatchError, match="not comparable"):
        load_bundle(bundle_dir)


# --------------------------------------------------------------------------- #
# Prediction output
# --------------------------------------------------------------------------- #


def test_prediction_returns_a_label_and_decision_scores_not_probabilities() -> None:
    service = InferenceService.from_bundle_dir()
    outcome = service.predict(_result())

    assert outcome.label in CLASS_LABELS
    assert set(outcome.decision_scores) == set(CLASS_LABELS)
    assert outcome.score_kind == SCORE_KIND == "decision_margin"
    assert outcome.is_margin_based is True
    assert outcome.ranking[0] == outcome.label
    assert outcome.margin >= 0.0
    assert outcome.model_version == "svm-v1.0.0"
    assert outcome.feature_set_version == FEATURE_SET_VERSION
    assert outcome.status == "clean"

    payload = outcome.as_dict()
    # No probability/confidence field in the output contract: the score is a margin.
    assert "confidence" not in payload
    assert "probability" not in payload
    assert not [key for key in payload if "confidence" in key or "probability" in key]
    assert payload["score_kind"] == "decision_margin"
    assert "not probabilities" in payload["score_note"]


def test_prediction_is_deterministic_for_the_same_row() -> None:
    service = InferenceService.from_bundle_dir()
    first = service.predict(_result())
    second = service.predict(_result())

    assert first.label == second.label
    assert first.decision_scores == pytest.approx(second.decision_scores)


def test_uncertain_result_with_nan_lesion_still_predicts() -> None:
    service = InferenceService.from_bundle_dir()
    values = np.asarray(_median_row(), dtype=np.float64)
    for name in LESION_DEPENDENT_FEATURES:
        values[FEATURE_NAMES.index(name)] = np.nan

    outcome = service.predict(
        _result(
            values.astype(np.float32),
            status="uncertain",
            lesion_reliable=False,
            missing=LESION_DEPENDENT_FEATURES,
            lesion_area_percentage=None,
        )
    )

    assert outcome.label in CLASS_LABELS
    assert outcome.lesion_reliable is False
    assert outcome.lesion_area_percentage is None
    assert outcome.status == "uncertain"
    assert "SMALL_IMAGE" in outcome.warnings
    assert tuple(outcome.missing_features) == LESION_DEPENDENT_FEATURES


def test_rejected_result_is_refused_without_zero_filling() -> None:
    service = InferenceService.from_bundle_dir()
    with pytest.raises(UnusableFeatureVectorError):
        service.predict(
            _result(
                None,
                status="rejected",
                lesion_reliable=False,
                missing=FEATURE_NAMES,
                lesion_area_percentage=None,
            )
        )


def test_feature_provenance_mismatch_is_refused() -> None:
    service = InferenceService.from_bundle_dir()

    with pytest.raises(ConfigMismatchError):
        service.predict(_result(quality_sha="f" * 64))
    with pytest.raises(SchemaMismatchError):
        service.predict(_result(schema_version="0.9.0"))
