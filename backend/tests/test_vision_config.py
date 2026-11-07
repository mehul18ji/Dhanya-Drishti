"""Tests for the validated YAML pipeline configuration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.vision.config import (
    DEFAULT_QUALITY_PATH,
    DEFAULT_SEGMENTATION_PATH,
    load_quality_config,
    load_segmentation_config,
)


def _dump_base(name: str) -> dict:
    path = DEFAULT_SEGMENTATION_PATH if name == "segmentation" else DEFAULT_QUALITY_PATH
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_default_configs_load_and_are_hashed() -> None:
    segmentation = load_segmentation_config()
    quality = load_quality_config()

    assert segmentation.segmentation_config_version == "seg-v2"
    assert quality.quality_config_version == "quality-v1"
    assert len(segmentation.content_sha256) == 64
    assert len(quality.content_sha256) == 64
    assert segmentation.content_sha256 == hashlib.sha256(
        DEFAULT_SEGMENTATION_PATH.read_bytes()
    ).hexdigest()
    assert segmentation.preprocessing.canvas_size <= segmentation.preprocessing.working_long_side


def test_config_hash_is_stable_across_loads() -> None:
    first = load_segmentation_config()
    second = load_segmentation_config()
    assert first.content_sha256 == second.content_sha256
    assert first.model_dump(exclude={"source_path", "content_sha256"}) == second.model_dump(
        exclude={"source_path", "content_sha256"}
    )


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    data = _dump_base("segmentation")
    data["preprocessing"]["typo_threshold"] = 123
    path = _write(tmp_path, "segmentation", data)

    with pytest.raises(ValidationError):
        load_segmentation_config(path)


def test_impossible_hue_range_is_rejected(tmp_path: Path) -> None:
    data = _dump_base("segmentation")
    data["leaf"]["hsv"]["green"]["h_min"] = 150
    data["leaf"]["hsv"]["green"]["h_max"] = 20
    path = _write(tmp_path, "segmentation", data)

    with pytest.raises(ValidationError):
        load_segmentation_config(path)


def test_even_morphology_kernel_is_rejected(tmp_path: Path) -> None:
    data = _dump_base("segmentation")
    data["leaf"]["morphology"]["open_kernel"] = 4
    path = _write(tmp_path, "segmentation", data)

    with pytest.raises(ValidationError):
        load_segmentation_config(path)


def test_canvas_cannot_exceed_working_image(tmp_path: Path) -> None:
    data = _dump_base("segmentation")
    data["preprocessing"]["canvas_size"] = 1024
    path = _write(tmp_path, "segmentation", data)

    with pytest.raises(ValidationError):
        load_segmentation_config(path)


def test_quality_warn_thresholds_must_be_inside_hard_limits(tmp_path: Path) -> None:
    data = _dump_base("quality")
    data["brightness"]["warn_mean_v_below"] = 10
    data["brightness"]["hard_reject_mean_v_below"] = 50
    path = _write(tmp_path, "quality", data)

    with pytest.raises(ValidationError):
        load_quality_config(path)


def test_dataset_calibrated_values_are_present() -> None:
    segmentation = load_segmentation_config()
    quality = load_quality_config()

    assert segmentation.leaf.fallback.enabled is True
    assert segmentation.leaf.fallback.leaf_green_fraction_threshold == pytest.approx(0.65)
    assert quality.dimensions.hard_reject_short_side_px == 64
    assert quality.dimensions.soft_warn_short_side_px == 224

    # The calibrated values that fixed the Phase 2 shadow leak must stay.
    assert segmentation.leaf.lab.min_chroma == 20
    assert segmentation.lesion.min_healthy_reference_fraction > 0.0

    # An archived copy of the superseded configuration must remain loadable.
    archived = DEFAULT_SEGMENTATION_PATH.parent / "archive" / "segmentation.seg-v1.yaml"
    assert archived.exists()
    assert load_segmentation_config(archived).segmentation_config_version == "seg-v1"

    # The config must remain JSON-serialisable for model manifests.
    payload = json.dumps(segmentation.model_dump())
    assert "seg-v2" in payload
