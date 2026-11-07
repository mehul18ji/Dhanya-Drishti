"""Run the Phase 2 segmentation pipeline over the whole dataset and record evidence.

Writes, under ``data/processed/segmentation_audit/<label>/`` (git-ignored):

- ``segmentation_audit.json`` — per-image rows, aggregates, config versions/hashes,
  dev-vs-held-out-test split, warning/rejection histograms and timings
- ``segmentation_audit.csv``  — the same per-image rows for spreadsheets
- ``panels/<label>__<stem>.png`` — 4-up review panel (input, leaf mask, lesion
  mask, overlay) for every image

and a small, committed evidence set under ``docs/segmentation_audit/``: the curated
panels named in ``CURATED_EXAMPLES``, their manifest and an aggregate summary.

Split discipline (split protocol v1): the 24 held-out test images are reported
separately and are **never** used to choose a threshold. Calibration looks only at
development images.

Usage (from the repository root)::

    python scripts/run_segmentation_audit.py
    python scripts/run_segmentation_audit.py --label baseline-seg-v1
    python scripts/run_segmentation_audit.py --only leaf_smut --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MANIFEST_PATH = PROCESSED_DIR / "dataset_manifest.csv"
SPLITS_DIR = REPO_ROOT / "data" / "splits"
TEST_PATH = SPLITS_DIR / "test.json"
AUDIT_ROOT = PROCESSED_DIR / "segmentation_audit"
DOCS_AUDIT_DIR = REPO_ROOT / "docs" / "segmentation_audit"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.vision.config import load_quality_config, load_segmentation_config  # noqa: E402
from app.vision.diagnostics import build_diagnostic_panel  # noqa: E402
from app.vision.pipeline import run_segmentation  # noqa: E402
from app.vision.preprocessing import ImageDecodeError  # noqa: E402

# Hard rejection codes that mean "no usable leaf", as opposed to a quality issue
# that still leaves the leaf analysable.
LEAF_FAILURE_CODES = {"NO_CLEAR_LEAF_FOUND", "LEAF_TOO_SMALL"}

# Curated, committed evidence set (PRD §25 Phase 2 "visual mask outputs").
# Chosen to show every class plus the difficult image families measured in Phase 1:
# extreme aspect ratios, tiny images, background-free close-ups.
CURATED_EXAMPLES: tuple[tuple[str, str], ...] = (
    (
        "data/raw/rice_leaf_diseases/Bacterial leaf blight/DSC_0365.JPG",
        "Bacterial leaf blight at the dataset's dominant 3.4:1 strip resolution",
    ),
    (
        "data/raw/rice_leaf_diseases/Bacterial leaf blight/DSC_0703.JPG",
        "Second Bacterial leaf blight leaf; confirms BLB is not a single template",
    ),
    (
        "data/raw/rice_leaf_diseases/Brown spot/DSC_0121.jpg",
        "Brown spot, near-square frame (1.33:1)",
    ),
    (
        "data/raw/rice_leaf_diseases/Brown spot/DSC_0105.jpg",
        "Brown spot at the dataset's most extreme 5.3:1 aspect ratio",
    ),
    (
        "data/raw/rice_leaf_diseases/Brown spot/DSC_0114.jpg",
        "Tiny image (296x88): exercises the soft small-image warning",
    ),
    (
        "data/raw/rice_leaf_diseases/Brown spot/DSC_0109.jpg",
        "Background-free close-up (>=71% leaf-green): exercises the full-frame fallback",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0504.jpg",
        "Leaf smut, near-square portrait-ish frame (1.25:1)",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0501.jpg",
        "Leaf smut at 5.0:1 aspect ratio",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0502.jpg",
        "Smallest image in the dataset (301x71); boundary case for the size gate",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0511.jpg",
        "Background-free close-up (>=74% leaf-green): full-frame fallback",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0508.jpg",
        "Pure leaf close-up named in the phase plan",
    ),
    (
        "data/raw/rice_leaf_diseases/Leaf smut/DSC_0515.jpg",
        "Pure leaf close-up named in the phase plan",
    ),
)


def _load_manifest() -> list[dict[str, str]]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            f"missing {MANIFEST_PATH.relative_to(REPO_ROOT)}; "
            "run `python scripts/audit_dataset.py` first"
        )
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def _load_test_paths() -> set[str]:
    if not TEST_PATH.exists():
        raise SystemExit(
            f"missing {TEST_PATH.relative_to(REPO_ROOT)}; "
            "run `python scripts/make_splits.py` first"
        )
    payload = json.loads(TEST_PATH.read_text(encoding="utf-8"))
    return {item["path"].replace("\\", "/") for item in payload["items"]}


def _panel_for(result, rel_path: str) -> np.ndarray:
    """Build the 4-up panel from the pipeline result (canvas when available)."""
    config_version = result.segmentation_config_version
    title = f"{rel_path} | {config_version}"

    if result.canvas_bgr is not None and result.canvas_leaf_mask is not None:
        lesion_mask = result.lesion.mask if result.lesion is not None else None
        return build_diagnostic_panel(
            result.canvas_bgr, result.canvas_leaf_mask, lesion_mask, title=title
        )

    # No leaf mask: review the working image against an empty mask so the failure
    # is still visually inspectable.
    working = result.working.bgr
    empty = np.zeros(working.shape[:2], dtype=np.uint8)
    return build_diagnostic_panel(working, empty, None, title=f"{title} | NO LEAF")


def _row_for(result, meta: dict[str, str], split: str, elapsed_ms: float) -> dict:
    leaf = result.leaf
    lesion = result.lesion
    warnings = [issue.code for issue in result.quality.warnings]
    rejections = [issue.code for issue in result.quality.rejections]
    leaf_failed = bool(set(rejections) & LEAF_FAILURE_CODES)

    return {
        "path": meta["path"].replace("\\", "/"),
        "filename": meta["filename"],
        "label": meta["label"],
        "split": split,
        "width": int(meta["width"]),
        "height": int(meta["height"]),
        "aspect_ratio": float(meta["aspect_ratio"]),
        "leaf_found": bool(leaf.found),
        "leaf_ok": bool(leaf.found and not leaf_failed),
        "leaf_method": leaf.method,
        "leaf_bbox": list(leaf.bbox) if leaf.bbox else None,
        "leaf_area_fraction": round(float(leaf.area_fraction), 6),
        "leaf_fill_ratio": round(float(leaf.fill_ratio), 6),
        "leaf_candidates": int(leaf.candidate_count),
        "full_frame_fallback": bool(leaf.used_full_frame_fallback),
        "multiple_leaves": bool(leaf.multiple_leaves),
        "lesion_area_fraction": round(float(lesion.lesion_area_fraction), 6) if lesion else None,
        "lesion_area_percentage": (
            round(float(lesion.lesion_area_fraction) * 100.0, 3) if lesion else None
        ),
        "lesion_count": int(lesion.lesion_count) if lesion else None,
        "lesion_reliable": bool(getattr(lesion, "reliable", True)) if lesion else None,
        "status": "rejected" if rejections else ("uncertain" if warnings else "clean"),
        "warnings": warnings,
        "rejections": rejections,
        "total_ms": round(float(elapsed_ms), 2),
        "stage_ms": result.stage_ms,
    }


def _aggregate(rows: list[dict], config, quality_config) -> dict:
    def _rate(part: int, total: int) -> float | None:
        return round(part / total, 4) if total else None

    def _block(subset: list[dict]) -> dict:
        total = len(subset)
        statuses = {key: sum(1 for row in subset if row["status"] == key) for key in ("clean", "uncertain", "rejected")}
        return {
            "images": total,
            "leaf_found": sum(1 for row in subset if row["leaf_found"]),
            "leaf_ok": sum(1 for row in subset if row["leaf_ok"]),
            "leaf_ok_fraction": _rate(sum(1 for row in subset if row["leaf_ok"]), total),
            "full_frame_fallback": sum(1 for row in subset if row["full_frame_fallback"]),
            "multiple_leaves": sum(1 for row in subset if row["multiple_leaves"]),
            "lesion_unreliable": sum(1 for row in subset if row["lesion_reliable"] is False),
            **statuses,
        }

    timings = [row["total_ms"] for row in rows]
    warnings_histogram: dict[str, int] = {}
    rejections_histogram: dict[str, int] = {}
    for row in rows:
        for code in row["warnings"]:
            warnings_histogram[code] = warnings_histogram.get(code, 0) + 1
        for code in row["rejections"]:
            rejections_histogram[code] = rejections_histogram.get(code, 0) + 1

    per_class = {}
    for label in sorted({row["label"] for row in rows}):
        per_class[label] = _block([row for row in rows if row["label"] == label])

    lesion_pcts = [
        row["lesion_area_percentage"]
        for row in rows
        if row["lesion_area_percentage"] is not None and row["leaf_ok"]
    ]

    return {
        "segmentation_config_version": config.segmentation_config_version,
        "segmentation_config_sha256": config.content_sha256,
        "quality_config_version": quality_config.quality_config_version,
        "quality_config_sha256": quality_config.content_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": _block(rows),
        "development": _block([row for row in rows if row["split"] == "development"]),
        "held_out_test": _block([row for row in rows if row["split"] == "test"]),
        "per_class": per_class,
        "warning_histogram": dict(sorted(warnings_histogram.items(), key=lambda item: -item[1])),
        "rejection_histogram": dict(sorted(rejections_histogram.items(), key=lambda item: -item[1])),
        "timing_ms": {
            "mean": round(mean(timings), 2) if timings else None,
            "p50": round(float(np.percentile(timings, 50)), 2) if timings else None,
            "p95": round(float(np.percentile(timings, 95)), 2) if timings else None,
            "max": round(max(timings), 2) if timings else None,
        },
        "lesion_area_percentage": {
            "mean": round(mean(lesion_pcts), 3) if lesion_pcts else None,
            "p50": round(float(np.percentile(lesion_pcts, 50)), 3) if lesion_pcts else None,
            "p95": round(float(np.percentile(lesion_pcts, 95)), 3) if lesion_pcts else None,
        },
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "path",
        "filename",
        "label",
        "split",
        "status",
        "leaf_found",
        "leaf_ok",
        "leaf_method",
        "leaf_area_fraction",
        "leaf_fill_ratio",
        "leaf_candidates",
        "full_frame_fallback",
        "multiple_leaves",
        "lesion_area_fraction",
        "lesion_area_percentage",
        "lesion_count",
        "lesion_reliable",
        "warnings",
        "rejections",
        "total_ms",
        "width",
        "height",
        "aspect_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = {key: row[key] for key in fieldnames if key not in {"warnings", "rejections"}}
            flat["warnings"] = "|".join(row["warnings"])
            flat["rejections"] = "|".join(row["rejections"])
            writer.writerow(flat)


def _write_curated(curated_dir: Path, panels_dir: Path, summary: dict) -> list[str]:
    curated_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for rel_path, reason in CURATED_EXAMPLES:
        panel = panels_dir / f"{rel_path.split('/')[-2].replace(' ', '_')}__{Path(rel_path).stem}.png"
        if not panel.exists():
            continue
        target = curated_dir / panel.name
        target.write_bytes(panel.read_bytes())
        items.append(
            {
                "source": rel_path,
                "panel": target.name,
                "reason": reason,
            }
        )

    manifest = {
        "segmentation_config_version": summary["segmentation_config_version"],
        "segmentation_config_sha256": summary["segmentation_config_sha256"],
        "quality_config_version": summary["quality_config_version"],
        "generated_at": summary["generated_at"],
        "regenerate_with": "python scripts/run_segmentation_audit.py",
        "items": items,
    }
    (curated_dir / "curated_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    committed_summary = {
        key: summary[key]
        for key in (
            "segmentation_config_version",
            "segmentation_config_sha256",
            "quality_config_version",
            "generated_at",
            "overall",
            "development",
            "held_out_test",
            "per_class",
            "warning_histogram",
            "rejection_histogram",
            "timing_ms",
        )
    }
    (curated_dir / "audit_summary.json").write_text(
        json.dumps(committed_summary, indent=2) + "\n", encoding="utf-8"
    )
    return [item["panel"] for item in items]


def _print_summary(summary: dict, output_dir: Path, curated_panels: list[str]) -> None:
    overall = summary["overall"]
    dev = summary["development"]
    test = summary["held_out_test"]

    print()
    print(f"segmentation audit : {summary['segmentation_config_version']} "
          f"(sha256 {summary['segmentation_config_sha256'][:12]})")
    print(f"quality config     : {summary['quality_config_version']} "
          f"(sha256 {summary['quality_config_sha256'][:12]})")
    print(f"images             : {overall['images']} "
          f"(development {dev['images']} / held-out test {test['images']})")
    print(f"plausible leaf mask: {overall['leaf_ok']}/{overall['images']} "
          f"({(overall['leaf_ok_fraction'] or 0) * 100:.1f}%) | "
          f"dev {dev['leaf_ok']}/{dev['images']} | test {test['leaf_ok']}/{test['images']}")
    print(f"status             : clean {overall['clean']}, uncertain {overall['uncertain']}, "
          f"rejected {overall['rejected']}")
    print(f"fallback / multi   : full-frame {overall['full_frame_fallback']} | "
          f"multiple leaves {overall['multiple_leaves']} | "
          f"lesion estimate unreliable {overall['lesion_unreliable']}")
    print(f"timing (ms)        : mean {summary['timing_ms']['mean']}, "
          f"p50 {summary['timing_ms']['p50']}, p95 {summary['timing_ms']['p95']}")

    if summary["rejection_histogram"]:
        print(f"rejections         : {summary['rejection_histogram']}")
    if summary["warning_histogram"]:
        print(f"warnings           : {summary['warning_histogram']}")

    for label, block in summary["per_class"].items():
        print(f"  {label:<24} leaf_ok {block['leaf_ok']}/{block['images']}  "
              f"clean {block['clean']}  uncertain {block['uncertain']}  "
              f"rejected {block['rejected']}")

    print()
    print(f"full audit  -> {output_dir.relative_to(REPO_ROOT)}")
    if curated_panels:
        print(f"curated set -> {DOCS_AUDIT_DIR.relative_to(REPO_ROOT)} "
              f"({len(curated_panels)} panels)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default=None,
                        help="output subdirectory name (default: the config version)")
    parser.add_argument("--config", default=None,
                        help="segmentation YAML to audit (default: backend/configs/segmentation.yaml)")
    parser.add_argument("--only", default=None,
                        help="only run images whose label or filename contains this text")
    parser.add_argument("--limit", type=int, default=None, help="stop after N images")
    parser.add_argument("--no-panels", action="store_true", help="skip PNG panel rendering")
    parser.add_argument("--no-curated", action="store_true",
                        help="do not refresh docs/segmentation_audit/")
    args = parser.parse_args(argv)

    segmentation_config = load_segmentation_config(args.config)
    quality_config = load_quality_config()
    label = args.label or segmentation_config.segmentation_config_version
    output_dir = AUDIT_ROOT / label
    panels_dir = output_dir / "panels"

    manifest = _load_manifest()
    test_paths = _load_test_paths()
    if args.only:
        needle = args.only.lower()
        manifest = [
            row for row in manifest
            if needle in row["label"].lower() or needle in row["filename"].lower()
        ]
    if args.limit:
        manifest = manifest[: args.limit]
    if not manifest:
        print("no images selected", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_panels:
        panels_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for index, meta in enumerate(manifest, start=1):
        rel_path = meta["path"].replace("\\", "/")
        split = "test" if rel_path in test_paths else "development"
        source = REPO_ROOT / rel_path

        try:
            result = run_segmentation(
                source,
                segmentation_config=segmentation_config,
                quality_config=quality_config,
            )
        except ImageDecodeError as exc:
            rows.append(
                {
                    "path": rel_path,
                    "filename": meta["filename"],
                    "label": meta["label"],
                    "split": split,
                    "width": int(meta["width"]),
                    "height": int(meta["height"]),
                    "aspect_ratio": float(meta["aspect_ratio"]),
                    "leaf_found": False,
                    "leaf_ok": False,
                    "leaf_method": "decode_failed",
                    "leaf_bbox": None,
                    "leaf_area_fraction": 0.0,
                    "leaf_fill_ratio": 0.0,
                    "leaf_candidates": 0,
                    "full_frame_fallback": False,
                    "multiple_leaves": False,
                    "lesion_area_fraction": None,
                    "lesion_area_percentage": None,
                    "lesion_count": None,
                    "lesion_reliable": None,
                    "status": "rejected",
                    "warnings": [],
                    "rejections": ["DECODE_FAILED"],
                    "total_ms": 0.0,
                    "stage_ms": {"error": str(exc)},
                }
            )
            continue

        row = _row_for(result, meta, split, result.stage_ms.get("total", 0.0))
        rows.append(row)

        if not args.no_panels:
            panel = _panel_for(result, rel_path)
            filename = f"{rel_path.split('/')[-2].replace(' ', '_')}__{Path(rel_path).stem}.png"
            cv2.imwrite(str(panels_dir / filename), panel)

        if index % 20 == 0 or index == len(manifest):
            print(f"  {index}/{len(manifest)} processed", flush=True)

    summary = _aggregate(rows, segmentation_config, quality_config)
    summary["scope"] = "partial" if (args.limit or args.only) else "full"
    summary["images_with_panels"] = 0 if args.no_panels else len(rows)

    (output_dir / "segmentation_audit.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output_dir / "segmentation_audit.csv", rows)

    curated_panels: list[str] = []
    if not args.no_curated and not args.no_panels and summary["scope"] == "full":
        curated_panels = _write_curated(DOCS_AUDIT_DIR, panels_dir, summary)

    _print_summary(summary, output_dir, curated_panels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
