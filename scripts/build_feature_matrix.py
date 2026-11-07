"""Build the versioned, split-aware feature matrix (Phase 3 M2).

Runs the frozen Phase 2 segmentation pipeline and the Phase 3 M1 feature
extractor over the approved images and writes a git-ignored, versioned output::

    data/processed/features/feature_set_v1.0.0/
        feature_matrix.csv          one row per image, schema-ordered columns
        feature_matrix.json         machine-readable metadata + per-split report
        feature_matrix_summary.md   human-readable summary

Split membership comes **only** from the frozen manifests in ``data/splits/``
(split protocol v1): ``test.json`` marks the 24 held-out test images and
``cv_folds.json`` marks the 96 development images. This script never re-splits,
re-labels, drops a row or changes membership.

Missing-value policy (decision P-13): unreliable lesion/spatial features stay
``NaN`` (written as ``NaN`` in the CSV), are counted in the report and are never
replaced with ``0.0``. A rejected image keeps its row with ``status=rejected``
and no feature values instead of being silently dropped.

No model is trained here.

Usage (from the repository root)::

    python scripts/build_feature_matrix.py
    python scripts/build_feature_matrix.py --only brown_spot --limit 5   # smoke run
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.vision.feature_extraction import (  # noqa: E402
    FEATURE_GROUPS,
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    FeatureExtractionResult,
    extract_features,
    feature_schema,
)

SPLITS_DIR = REPO_ROOT / "data" / "splits"
TEST_PATH = SPLITS_DIR / "test.json"
CV_FOLDS_PATH = SPLITS_DIR / "cv_folds.json"
SPLIT_MANIFEST_PATH = SPLITS_DIR / "split_manifest.json"
OUTPUT_ROOT = REPO_ROOT / "data" / "processed" / "features"

SPLIT_DEVELOPMENT = "development"
SPLIT_TEST = "held_out_test"
SPLITS = (SPLIT_DEVELOPMENT, SPLIT_TEST)

CLASS_SLUGS = {
    "Bacterial leaf blight": "bacterial_leaf_blight",
    "Brown spot": "brown_spot",
    "Leaf smut": "leaf_smut",
}

IDENTITY_COLUMNS = ("image_id", "relative_path", "label", "split", "cv_fold")
STATE_COLUMNS = (
    "status",
    "lesion_reliable",
    "lesion_area_percentage",
    "segmentation_config_version",
    "segmentation_config_sha256",
    "quality_config_version",
    "quality_config_sha256",
)
TRAILING_COLUMNS = ("warnings", "rejections", "missing_features")
MATRIX_COLUMNS = IDENTITY_COLUMNS + STATE_COLUMNS + FEATURE_NAMES + TRAILING_COLUMNS

#: The single spelling used for a missing value in the CSV. pandas/numpy read
#: this back as a real NaN, so an uncalibrated lesion is never mistaken for 0.
NAN_CELL = "NaN"


# --------------------------------------------------------------------------- #
# Split manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SplitEntry:
    """One approved image and its frozen split assignment."""

    image_id: str
    relative_path: str
    label: str
    split: str
    cv_fold: int | None


def _normalise(relative_path: str) -> str:
    return relative_path.replace("\\", "/")


def _label_from_path(relative_path: str) -> str:
    parts = _normalise(relative_path).split("/")
    if len(parts) < 2:
        raise SystemExit(f"cannot derive a class folder from {relative_path!r}")
    folder = parts[-2]
    if folder in CLASS_SLUGS:
        return CLASS_SLUGS[folder]
    return folder.strip().lower().replace(" ", "_")


def _image_id(label: str, relative_path: str) -> str:
    """Stable identifier: class slug plus file stem (matches the audit panels)."""
    return f"{label}__{Path(relative_path).stem}"


def load_split_entries(
    *,
    test_path: Path = TEST_PATH,
    cv_folds_path: Path = CV_FOLDS_PATH,
) -> list[SplitEntry]:
    """Read the frozen split manifests; never invents or reorders assignments."""
    test_payload = json.loads(Path(test_path).read_text(encoding="utf-8"))
    folds_payload = json.loads(Path(cv_folds_path).read_text(encoding="utf-8"))

    entries: dict[str, SplitEntry] = {}
    for item in test_payload["items"]:
        relative_path = _normalise(item["path"])
        label = item.get("label") or _label_from_path(relative_path)
        entries[relative_path] = SplitEntry(
            image_id=_image_id(label, relative_path),
            relative_path=relative_path,
            label=label,
            split=SPLIT_TEST,
            cv_fold=None,
        )

    # Development images appear in ``train`` on four folds and in ``validation``
    # on exactly one; the validation fold is the meaningful CV assignment.
    development_paths: set[str] = set()
    fold_assignment: dict[str, int] = {}
    for fold in folds_payload["folds"]:
        for key in ("train", "validation"):
            for raw in fold.get(key, []):
                development_paths.add(_normalise(raw))
    for fold in folds_payload["folds"]:
        index = int(fold["fold"])
        for raw in fold.get("validation", []):
            fold_assignment[_normalise(raw)] = index

    for relative_path in sorted(development_paths):
        if relative_path in entries:
            raise SystemExit(
                f"split manifests disagree: {relative_path} is both held-out test "
                "and development"
            )
        label = _label_from_path(relative_path)
        entries[relative_path] = SplitEntry(
            image_id=_image_id(label, relative_path),
            relative_path=relative_path,
            label=label,
            split=SPLIT_DEVELOPMENT,
            cv_fold=fold_assignment.get(relative_path),
        )

    seen: dict[str, str] = {}
    for entry in entries.values():
        if entry.image_id in seen:
            raise SystemExit(
                f"duplicate image_id {entry.image_id!r} for "
                f"{seen[entry.image_id]!r} and {entry.relative_path!r}"
            )
        seen[entry.image_id] = entry.relative_path

    return sorted(
        entries.values(), key=lambda entry: (entry.split, entry.label, entry.relative_path)
    )


# --------------------------------------------------------------------------- #
# Matrix construction
# --------------------------------------------------------------------------- #

Extractor = Callable[[Path], FeatureExtractionResult]


@dataclass(frozen=True)
class MatrixRow:
    """One image's identity, split assignment and extracted feature result."""

    entry: SplitEntry
    result: FeatureExtractionResult

    def as_record(self) -> dict[str, str]:
        """Flat CSV record in :data:`MATRIX_COLUMNS` order."""
        record: dict[str, str] = {
            "image_id": self.entry.image_id,
            "relative_path": self.entry.relative_path,
            "label": self.entry.label,
            "split": self.entry.split,
            "cv_fold": "" if self.entry.cv_fold is None else str(self.entry.cv_fold),
            "status": self.result.status,
            "lesion_reliable": "True" if self.result.lesion_reliable else "False",
            "lesion_area_percentage": _format_number(self.result.lesion_area_percentage),
            "segmentation_config_version": self.result.segmentation_config_version,
            "segmentation_config_sha256": self.result.segmentation_config_sha256,
            "quality_config_version": self.result.quality_config_version,
            "quality_config_sha256": self.result.quality_config_sha256,
            "warnings": "|".join(self.result.warnings),
            "rejections": "|".join(self.result.rejections),
            "missing_features": "|".join(self.result.missing_features),
        }

        values = self.result.values
        for index, name in enumerate(FEATURE_NAMES):
            if values is None:
                record[name] = NAN_CELL
            else:
                record[name] = _format_number(float(values[index]))
        return {column: record[column] for column in MATRIX_COLUMNS}


def _format_number(value: float | None) -> str:
    """Format a feature value, keeping 'missing' and 'measured zero' distinct."""
    if value is None:
        return NAN_CELL
    number = float(value)
    if math.isnan(number):
        return NAN_CELL
    if math.isinf(number):
        raise ValueError("feature extractor produced an infinite value")
    return f"{number:.10g}"


def build_matrix(
    entries: Sequence[SplitEntry],
    *,
    extract: Extractor = extract_features,
    log: Callable[[str], None] = print,
) -> list[MatrixRow]:
    """Extract one row per entry using the shared Phase 2 + Phase 3 code path."""
    rows: list[MatrixRow] = []
    total = len(entries)
    for index, entry in enumerate(entries, start=1):
        path = REPO_ROOT / entry.relative_path
        result = extract(path)
        rows.append(MatrixRow(entry=entry, result=result))
        log(
            f"  [{index}/{total}] {entry.split:<14} {entry.label:<24} "
            f"{result.status:<9} lesion_reliable={result.lesion_reliable}"
        )
    return rows


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def _split_block(rows: Sequence[MatrixRow]) -> dict:
    status_counts = {"clean": 0, "uncertain": 0, "rejected": 0}
    class_counts: dict[str, int] = {}
    lesion_reliable = 0
    rows_with_values = 0
    for row in rows:
        status_counts[row.result.status] = status_counts.get(row.result.status, 0) + 1
        class_counts[row.entry.label] = class_counts.get(row.entry.label, 0) + 1
        if row.result.lesion_reliable:
            lesion_reliable += 1
        if row.result.values is not None:
            rows_with_values += 1
    return {
        "images": len(rows),
        "rows": len(rows),
        "rows_with_feature_values": rows_with_values,
        "class_counts": dict(sorted(class_counts.items())),
        "status_counts": status_counts,
        "lesion_reliable": lesion_reliable,
        "lesion_unreliable": len(rows) - lesion_reliable,
        "cv_folds": sorted(
            {row.entry.cv_fold for row in rows if row.entry.cv_fold is not None}
        ),
    }


def _missing_by_group(rows: Sequence[MatrixRow]) -> dict[str, dict[str, int]]:
    """Count NaN cells per feature group, per split (never imputed)."""
    block: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        subset = [row for row in rows if row.entry.split == split]
        group_counts: dict[str, int] = {}
        for group, names in FEATURE_GROUPS.items():
            missing = 0
            for row in subset:
                for name in names:
                    if name in row.result.missing_features:
                        missing += 1
            group_counts[group] = missing
        block[split] = group_counts
    return block


def _provenance() -> dict:
    if not SPLIT_MANIFEST_PATH.exists():
        return {}
    payload = json.loads(SPLIT_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        "split_version": payload.get("split_version"),
        "seed": payload.get("seed"),
        "dataset_version": payload.get("dataset_version"),
        "dataset_checksum_sha256": payload.get("dataset_checksum_sha256"),
        "dataset_manifest_sha256": payload.get("dataset_manifest_sha256"),
        "duplicate_groups_sha256": payload.get("duplicate_groups_sha256"),
        "counts": payload.get("counts"),
        "generated_by": "scripts/build_feature_matrix.py",
    }


def build_report(
    rows: Sequence[MatrixRow],
    *,
    generated_at: str | None = None,
    scope: str = "full",
) -> dict:
    """Machine-readable metadata + per-split report for the matrix."""
    first = rows[0].result if rows else None
    return {
        "feature_set_version": FEATURE_SET_VERSION,
        "schema": feature_schema(),
        "matrix_columns": list(MATRIX_COLUMNS),
        "scope": scope,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": len(rows),
        "splits": {split: _split_block([r for r in rows if r.entry.split == split]) for split in SPLITS},
        "missing_values_by_group": _missing_by_group(rows),
        "nan_policy": (
            "Unreliable lesion/spatial features are real NaN cells (decision P-13) and "
            "are never replaced with 0.0; no row is dropped. Imputation, if any, must be "
            "fitted per training fold inside the scikit-learn pipeline."
        ),
        "segmentation_config_version": first.segmentation_config_version if first else "",
        "segmentation_config_sha256": first.segmentation_config_sha256 if first else "",
        "quality_config_version": first.quality_config_version if first else "",
        "quality_config_sha256": first.quality_config_sha256 if first else "",
        "provenance": _provenance(),
        "artifacts": {
            "matrix_csv": "feature_matrix.csv",
            "report_json": "feature_matrix.json",
            "summary_markdown": "feature_matrix_summary.md",
        },
    }


def render_summary(report: dict) -> str:
    """Human-readable Markdown summary for docs / project status."""
    lines: list[str] = []
    lines.append(f"# Feature matrix — feature set v{report['feature_set_version']}")
    lines.append("")
    lines.append(f"Generated: `{report['generated_at']}` | scope: **{report['scope']}**")
    provenance = report.get("provenance", {})
    if provenance:
        lines.append(
            f"Dataset: `{provenance.get('dataset_version')}` | split protocol "
            f"`{provenance.get('split_version')}` (seed {provenance.get('seed')})"
        )
    lines.append("")
    lines.append(f"Rows: **{report['row_count']}** | columns: {len(report['matrix_columns'])} "
                 f"({len(FEATURE_NAMES)} schema features)")
    lines.append("")
    lines.append("## Rows per split")
    lines.append("")
    lines.append("| split | images | rows with values | clean | uncertain | rejected | lesion unreliable |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for split, block in report["splits"].items():
        status = block["status_counts"]
        lines.append(
            f"| {split} | {block['images']} | {block['rows_with_feature_values']} | "
            f"{status.get('clean', 0)} | {status.get('uncertain', 0)} | "
            f"{status.get('rejected', 0)} | {block['lesion_unreliable']} |"
        )
    lines.append("")
    lines.append("## Class counts")
    lines.append("")
    labels = sorted({label for block in report["splits"].values() for label in block["class_counts"]})
    lines.append("| split | " + " | ".join(labels) + " |")
    lines.append("|---|" + "---:|" * len(labels))
    for split, block in report["splits"].items():
        counts = [str(block["class_counts"].get(label, 0)) for label in labels]
        lines.append(f"| {split} | " + " | ".join(counts) + " |")
    lines.append("")
    lines.append("## Missing values by feature group (NaN cells, never imputed)")
    lines.append("")
    groups = list(FEATURE_GROUPS)
    lines.append("| group | features | " + " | ".join(report["splits"]) + " |")
    lines.append("|---|---:|" + "---:|" * len(report["splits"]))
    for group in groups:
        cells = [
            str(report["missing_values_by_group"][split][group]) for split in report["splits"]
        ]
        lines.append(f"| {group} | {len(FEATURE_GROUPS[group])} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Schema: `{report['schema']['schema_name']}` v{report['feature_set_version']} "
                 f"({report['schema']['feature_count']} features)")
    lines.append(f"- Segmentation config: `{report['segmentation_config_version']}` "
                 f"(sha256 `{report['segmentation_config_sha256']}`)")
    lines.append(f"- Quality config: `{report['quality_config_version']}` "
                 f"(sha256 `{report['quality_config_sha256']}`)")
    lines.append(f"- NaN policy: {report['nan_policy']}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    rows: Sequence[MatrixRow],
    output_dir: Path,
    *,
    scope: str = "full",
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write the CSV, JSON report and Markdown summary into ``output_dir``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "feature_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MATRIX_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_record())

    report = build_report(rows, generated_at=generated_at, scope=scope)
    json_path = output_dir / "feature_matrix.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    summary_path = output_dir / "feature_matrix_summary.md"
    summary_path.write_text(render_summary(report), encoding="utf-8")

    return {"csv": csv_path, "json": json_path, "summary": summary_path, "report": report}


def default_output_dir(feature_set_version: str = FEATURE_SET_VERSION) -> Path:
    """Versioned, git-ignored location for a full matrix build."""
    return OUTPUT_ROOT / f"feature_set_v{feature_set_version}"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=None, help="override the output directory")
    parser.add_argument("--only", default=None, help="only images whose label/path contains this text")
    parser.add_argument("--limit", type=int, default=None, help="stop after N images")
    args = parser.parse_args(argv)

    entries = load_split_entries()
    if args.only:
        needle = args.only.lower()
        entries = [
            entry
            for entry in entries
            if needle in entry.label.lower() or needle in entry.relative_path.lower()
        ]
    if args.limit:
        entries = entries[: args.limit]
    if not entries:
        print("no images selected", file=sys.stderr)
        return 1

    partial = bool(args.only or args.limit)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else default_output_dir() / ("_partial" if partial else "")
    )

    print(f"feature set        : v{FEATURE_SET_VERSION} ({len(FEATURE_NAMES)} features)")
    print(f"images             : {len(entries)} (from the frozen split manifests)")
    print(f"output             : {output_dir.relative_to(REPO_ROOT) if output_dir.is_relative_to(REPO_ROOT) else output_dir}")
    print()

    rows = build_matrix(entries)
    written = write_outputs(rows, output_dir, scope="partial" if partial else "full")
    report = written["report"]

    for split in SPLITS:
        status = report["splits"][split]["status_counts"]
        print(
            f"{split:<14} images {report['splits'][split]['images']:>3} | "
            f"clean {status.get('clean', 0):>3} uncertain {status.get('uncertain', 0):>3} "
            f"rejected {status.get('rejected', 0):>3} | "
            f"lesion unreliable {report['splits'][split]['lesion_unreliable']:>3}"
        )
    print()
    for key in ("csv", "json", "summary"):
        path = written[key]
        print(f"wrote {key:<8} -> {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
