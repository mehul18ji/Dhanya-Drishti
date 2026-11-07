"""Audit the raw rice-leaf dataset and emit a reproducible manifest.

Phase 1 deliverable (see PHASE_PLAN.txt §Phases / Phase 1).

Reads (never writes) every image under ``data/raw/rice_leaf_diseases/`` and produces:

- ``data/processed/dataset_manifest.csv``  one row per image
- ``data/processed/dataset_audit.json``    class counts, resolution ranges,
                                           tiny images, full-frame close-ups,
                                           quality metric percentiles,
                                           exact-duplicate groups and the
                                           dataset checksum (dataset_version)

Usage (from the repository root)::

    python scripts/audit_dataset.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "rice_leaf_diseases"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MANIFEST_PATH = PROCESSED_DIR / "dataset_manifest.csv"
SUMMARY_PATH = PROCESSED_DIR / "dataset_audit.json"

# Folder name (as shipped in the Kaggle download) -> stable label slug.
CLASS_SLUGS: dict[str, str] = {
    "Bacterial leaf blight": "bacterial_leaf_blight",
    "Brown spot": "brown_spot",
    "Leaf smut": "leaf_smut",
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Analysis thresholds used only for reporting, not for rejection.
TINY_SHORT_SIDE = 128
FULL_FRAME_GREEN_RATIO = 0.70
ANALYSIS_LONG_SIDE = 400

# OpenCV HSV ranges (H is 0-179 in OpenCV, not 0-360).
GREEN_HSV_LOWER = np.array([25, 40, 25], dtype=np.uint8)
GREEN_HSV_UPPER = np.array([95, 255, 255], dtype=np.uint8)

FIELDNAMES = [
    "path",
    "label",
    "folder",
    "filename",
    "width",
    "height",
    "short_side",
    "aspect_ratio",
    "bytes",
    "md5",
    "format",
    "mode",
    "exif_orientation",
    "decode_ok",
    "leaf_green_fraction",
    "mean_brightness",
    "overexposed_fraction",
    "laplacian_variance",
]


def md5_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analysis_scale(bgr: np.ndarray) -> np.ndarray:
    """Downscale for metric computation only (never used for training)."""
    height, width = bgr.shape[:2]
    scale = ANALYSIS_LONG_SIDE / max(height, width)
    if scale >= 1:
        return bgr
    return cv2.resize(
        bgr,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def image_metrics(bgr: np.ndarray) -> dict[str, float]:
    """Scale-independent metrics used for quality-threshold calibration."""
    small = analysis_scale(bgr)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv, GREEN_HSV_LOWER, GREEN_HSV_UPPER) > 0
    value = hsv[:, :, 2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    total = float(small.shape[0] * small.shape[1])
    return {
        "leaf_green_fraction": round(float(green_mask.sum()) / total, 6),
        "mean_brightness": round(float(value.mean()), 3),
        "overexposed_fraction": round(float((value >= 245).sum()) / total, 6),
        # Variance of the Laplacian: lower means blurrier.
        "laplacian_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
    }


def audit_image(path: Path, label: str, folder: str) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "label": label,
        "folder": folder,
        "filename": path.name,
        "width": "",
        "height": "",
        "short_side": "",
        "aspect_ratio": "",
        "bytes": path.stat().st_size,
        "md5": md5_of_file(path),
        "format": "",
        "mode": "",
        "exif_orientation": 1,
        "decode_ok": False,
        "leaf_green_fraction": "",
        "mean_brightness": "",
        "overexposed_fraction": "",
        "laplacian_variance": "",
    }

    try:
        with Image.open(path) as image:
            row["format"] = image.format or ""
            row["mode"] = image.mode
            row["width"], row["height"] = image.size
            row["short_side"] = min(image.size)
            row["aspect_ratio"] = round(max(image.size) / min(image.size), 4)
            exif = image.getexif()
            row["exif_orientation"] = int(exif.get(274, 1) or 1)
    except Exception as exc:  # pragma: no cover - corrupt-file path is data dependent
        print(f"[warn] Pillow could not read {path}: {exc}", file=sys.stderr)

    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is not None:
        row["decode_ok"] = True
        row.update(image_metrics(bgr))
    else:
        print(f"[warn] OpenCV could not decode {path}", file=sys.stderr)

    return row


def percentile(values: list[float], q: float) -> float:
    return round(float(np.percentile(values, q)), 4) if values else 0.0


def build_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    by_class: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_class[str(row["label"])].append(row)

    md5_groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        md5_groups[str(row["md5"])].append(str(row["path"]))
    exact_duplicates = [sorted(group) for group in md5_groups.values() if len(group) > 1]

    # Deterministic dataset checksum: (md5, path) pairs sorted by path.
    checksum_source = "\n".join(
        f"{row['md5']}  {row['path']}" for row in sorted(rows, key=lambda r: str(r["path"]))
    )
    dataset_checksum = hashlib.sha256(checksum_source.encode("utf-8")).hexdigest()

    classes: dict[str, object] = {}
    total_bytes = 0
    for label in sorted(by_class):
        class_rows = by_class[label]
        widths = [int(r["width"]) for r in class_rows if r["width"] != ""]
        heights = [int(r["height"]) for r in class_rows if r["height"] != ""]
        aspects = [float(r["aspect_ratio"]) for r in class_rows if r["aspect_ratio"] != ""]
        sizes = [int(r["bytes"]) for r in class_rows]
        total_bytes += sum(sizes)
        classes[label] = {
            "images": len(class_rows),
            "bytes": sum(sizes),
            "width_min": min(widths) if widths else None,
            "width_max": max(widths) if widths else None,
            "height_min": min(heights) if heights else None,
            "height_max": max(heights) if heights else None,
            "aspect_min": min(aspects) if aspects else None,
            "aspect_max": max(aspects) if aspects else None,
            "distinct_resolutions": len({(int(r["width"]), int(r["height"])) for r in class_rows}),
            "files": sorted(str(r["path"]) for r in class_rows),
        }

    tiny = [
        {
            "path": str(r["path"]),
            "width": r["width"],
            "height": r["height"],
            "short_side": r["short_side"],
        }
        for r in sorted(rows, key=lambda r: int(r["short_side"]))
        if r["short_side"] != "" and int(r["short_side"]) < TINY_SHORT_SIDE
    ]

    full_frame = [
        {
            "path": str(r["path"]),
            "leaf_green_fraction": r["leaf_green_fraction"],
        }
        for r in sorted(rows, key=lambda r: float(r["leaf_green_fraction"]))
        if r["leaf_green_fraction"] != ""
        and float(r["leaf_green_fraction"]) > FULL_FRAME_GREEN_RATIO
    ]

    metrics = {
        "leaf_green_fraction": [float(r["leaf_green_fraction"]) for r in rows if r["leaf_green_fraction"] != ""],
        "mean_brightness": [float(r["mean_brightness"]) for r in rows if r["mean_brightness"] != ""],
        "overexposed_fraction": [float(r["overexposed_fraction"]) for r in rows if r["overexposed_fraction"] != ""],
        "laplacian_variance": [float(r["laplacian_variance"]) for r in rows if r["laplacian_variance"] != ""],
    }

    return {
        "dataset_version": f"ds-{dataset_checksum[:12]}",
        "dataset_checksum_sha256": dataset_checksum,
        "image_count": len(rows),
        "class_counts": {label: len(class_rows) for label, class_rows in sorted(by_class.items())},
        "classes": classes,
        "total_bytes": total_bytes,
        "decode_failures": [str(r["path"]) for r in rows if not r["decode_ok"]],
        "exif_orientations": dict(sorted(Counter(int(r["exif_orientation"]) for r in rows).items())),
        "extensions": dict(sorted(Counter(Path(str(r["path"])).suffix.lower() for r in rows).items())),
        "exact_duplicate_groups": exact_duplicates,
        "tiny_images_short_side_below": TINY_SHORT_SIDE,
        "tiny_images": tiny,
        "full_frame_green_ratio_above": FULL_FRAME_GREEN_RATIO,
        "full_frame_images": full_frame,
        "quality_metric_percentiles": {
            name: {f"p{q}": percentile(values, q) for q in (5, 25, 50, 75, 95)}
            for name, values in metrics.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help=f"Dataset root (default: {RAW_DIR})",
    )
    args = parser.parse_args()

    raw_dir: Path = args.raw_dir
    if not raw_dir.is_dir():
        print(f"[error] dataset directory not found: {raw_dir}", file=sys.stderr)
        return 2

    class_dirs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    unknown = [path.name for path in class_dirs if path.name not in CLASS_SLUGS]
    if unknown:
        print(f"[error] unrecognised class folders: {unknown}", file=sys.stderr)
        print(f"[error] known folders: {sorted(CLASS_SLUGS)}", file=sys.stderr)
        return 2

    rows: list[dict[str, object]] = []
    for class_dir in class_dirs:
        label = CLASS_SLUGS[class_dir.name]
        for path in sorted(class_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                rows.append(audit_image(path, label, class_dir.name))

    if not rows:
        print("[error] no images found", file=sys.stderr)
        return 2

    rows.sort(key=lambda r: (str(r["label"]), str(r["filename"]).lower()))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    summary = build_summary(rows)
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Manifest : {MANIFEST_PATH.relative_to(REPO_ROOT)}  ({len(rows)} images)")
    print(f"Summary  : {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    print(f"Dataset  : {summary['dataset_version']}")
    print("Classes  :", summary["class_counts"])
    print(f"Tiny     : {len(summary['tiny_images'])} images with short side < {TINY_SHORT_SIDE}px")
    print(
        "Close-ups:",
        len(summary["full_frame_images"]),
        f"images with >{int(FULL_FRAME_GREEN_RATIO * 100)}% leaf-green pixels",
    )
    print(f"Exact duplicate groups: {len(summary['exact_duplicate_groups'])}")
    print(f"Decode failures: {len(summary['decode_failures'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
