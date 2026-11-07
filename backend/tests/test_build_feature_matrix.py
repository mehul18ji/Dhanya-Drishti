"""Tests for the split-aware feature-matrix build (Phase 3 M2).

No raw dataset is required: split-manifest reading uses the committed
``data/splits/*.json`` files, and matrix construction injects a stub extractor
so nothing is segmented or cached here.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    FeatureExtractionResult,
)
from scripts.build_feature_matrix import (  # noqa: E402
    MATRIX_COLUMNS,
    NAN_CELL,
    SplitEntry,
    build_matrix,
    load_split_entries,
    write_outputs,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _result(
    values: np.ndarray | None,
    *,
    status: str = "clean",
    lesion_reliable: bool = True,
    missing: tuple[str, ...] = (),
    lesion_area_percentage: float | None = 5.0,
    warnings: tuple[str, ...] = (),
) -> FeatureExtractionResult:
    return FeatureExtractionResult(
        values=values,
        status=status,  # type: ignore[arg-type]
        lesion_reliable=lesion_reliable,
        lesion_reference_available=lesion_reliable,
        lesion_area_percentage=lesion_area_percentage,
        warnings=warnings,
        rejections=(),
        missing_features=tuple(missing),
        segmentation_config_version="seg-v2",
        segmentation_config_sha256=SHA_A,
        quality_config_version="quality-v1",
        quality_config_sha256=SHA_B,
    )


def _entry(
    label: str,
    stem: str,
    split: str,
    fold: int | None,
) -> SplitEntry:
    return SplitEntry(
        image_id=f"{label}__{stem}",
        relative_path=f"data/raw/rice_leaf_diseases/{label}/{stem}.jpg",
        label=label,
        split=split,
        cv_fold=fold,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_matrix_columns_follow_the_schema_order(tmp_path: Path) -> None:
    entry = _entry("brown_spot", "DSC_0105", "development", 2)
    values = np.arange(len(FEATURE_NAMES), dtype=np.float32)

    rows = build_matrix([entry], extract=lambda _: _result(values), log=lambda _: None)
    record = rows[0].as_record()

    assert list(record) == list(MATRIX_COLUMNS)
    # Positional identity: column i carries feature i, so a saved model stays valid.
    for index, name in enumerate(FEATURE_NAMES):
        assert float(record[name]) == pytest.approx(float(index))

    assert record["image_id"] == "brown_spot__DSC_0105"
    assert record["relative_path"] == entry.relative_path
    assert record["label"] == "brown_spot"
    assert record["split"] == "development"
    assert record["cv_fold"] == "2"

    written = write_outputs(rows, tmp_path)
    report = written["report"]
    assert report["feature_set_version"] == FEATURE_SET_VERSION
    assert report["matrix_columns"] == list(MATRIX_COLUMNS)
    assert report["row_count"] == 1
    # CSV header is the same order as the schema-derived column list.
    with written["csv"].open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header == list(MATRIX_COLUMNS)


def test_split_assignments_come_from_the_frozen_manifests() -> None:
    entries = load_split_entries()

    assert len(entries) == 120
    held_out = [entry for entry in entries if entry.split == "held_out_test"]
    development = [entry for entry in entries if entry.split == "development"]
    assert len(held_out) == 24
    assert len(development) == 96

    # No overlap, no duplicate identifiers, no re-splitting.
    assert not (
        {entry.relative_path for entry in held_out}
        & {entry.relative_path for entry in development}
    )
    assert len({entry.image_id for entry in entries}) == 120

    test_per_class: dict[str, int] = {}
    for entry in held_out:
        test_per_class[entry.label] = test_per_class.get(entry.label, 0) + 1
    assert sorted(test_per_class) == ["bacterial_leaf_blight", "brown_spot", "leaf_smut"]
    assert set(test_per_class.values()) == {8}

    # Held-out images carry no CV fold; development images are spread over all 5.
    assert {entry.cv_fold for entry in held_out} == {None}
    assert {entry.cv_fold for entry in development} == {0, 1, 2, 3, 4}


def test_unreliable_lesion_values_stay_nan_in_the_csv(tmp_path: Path) -> None:
    values = np.arange(len(FEATURE_NAMES), dtype=np.float32)
    for name in LESION_DEPENDENT_FEATURES:
        values[FEATURE_NAMES.index(name)] = np.nan

    entry = _entry("leaf_smut", "DSC_0508", "development", 1)
    rows = build_matrix(
        [entry],
        extract=lambda _: _result(
            values,
            status="uncertain",
            lesion_reliable=False,
            missing=LESION_DEPENDENT_FEATURES,
            lesion_area_percentage=None,
            warnings=("LESION_REFERENCE_UNAVAILABLE",),
        ),
        log=lambda _: None,
    )
    written = write_outputs(rows, tmp_path)
    records = _read_csv(written["csv"])

    assert len(records) == 1, "an unreliable lesion must not drop the row"
    record = records[0]
    for name in LESION_DEPENDENT_FEATURES:
        assert record[name] == NAN_CELL, f"{name} must be NaN, not 0"
        assert record[name] != "0"
    assert record["lesion_area_percentage"] == NAN_CELL
    assert record["lesion_reliable"] == "False"
    assert record["status"] == "uncertain"
    assert "LESION_REFERENCE_UNAVAILABLE" in record["warnings"]
    assert record["missing_features"] == "|".join(LESION_DEPENDENT_FEATURES)

    report = written["report"]
    assert report["missing_values_by_group"]["development"]["lesion"] == 6
    assert report["missing_values_by_group"]["development"]["spatial"] == 9
    assert report["missing_values_by_group"]["development"]["colour"] == 0
    assert report["splits"]["development"]["lesion_unreliable"] == 1
    assert report["splits"]["development"]["status_counts"]["uncertain"] == 1


def test_measured_zero_is_written_as_zero_not_nan(tmp_path: Path) -> None:
    zeros = np.zeros(len(FEATURE_NAMES), dtype=np.float32)
    entry = _entry("bacterial_leaf_blight", "DSC_0365", "development", 0)

    rows = build_matrix([entry], extract=lambda _: _result(zeros), log=lambda _: None)
    record = rows[0].as_record()

    assert record["lesion_area_ratio"] == "0"
    assert record["lesion_area_percentage"] == "5"
    assert record["missing_features"] == ""


def test_rejected_rows_are_kept_and_reported_per_split(tmp_path: Path) -> None:
    development = _entry("brown_spot", "DSC_0105", "development", 3)
    held_out = _entry("leaf_smut", "DSC_0501", "held_out_test", None)

    rejected_path = REPO_ROOT / held_out.relative_path

    def extract(path: Path) -> FeatureExtractionResult:
        if Path(path) == rejected_path:
            return _result(
                None,
                status="rejected",
                lesion_reliable=False,
                missing=FEATURE_NAMES,
                lesion_area_percentage=None,
            )
        return _result(np.zeros(len(FEATURE_NAMES), dtype=np.float32))

    rows = build_matrix([development, held_out], extract=extract, log=lambda _: None)
    written = write_outputs(rows, tmp_path)
    records = _read_csv(written["csv"])

    assert len(records) == 2, "rejected images keep a row"
    rejected = next(record for record in records if record["status"] == "rejected")
    assert rejected["split"] == "held_out_test"
    assert all(rejected[name] == NAN_CELL for name in FEATURE_NAMES)

    report = written["report"]
    assert report["splits"]["development"]["status_counts"]["clean"] == 1
    assert report["splits"]["held_out_test"]["status_counts"]["rejected"] == 1
    assert report["splits"]["development"]["images"] == 1
    assert report["splits"]["held_out_test"]["images"] == 1

    summary = written["summary"].read_text(encoding="utf-8")
    assert "development" in summary and "held_out_test" in summary
    assert f"v{FEATURE_SET_VERSION}" in summary
