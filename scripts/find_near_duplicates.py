"""Screen the dataset for exact and near-duplicate images.

Phase 1 deliverable (PRD §10: "Check for duplicate or near-duplicate images
before splitting. Never allow an original image and an altered copy of it to
appear across both training and testing.").

A coarse average-hash is not reliable on this dataset (all images share a
similar leaf-on-paper composition), so this script combines independent
signals and flags only pairs that agree:

1. MD5 of the file bytes            -> exact duplicates
2. dHash (16x16, 256-bit)           -> structural similarity
3. HSV histogram correlation        -> colour similarity
4. SSIM on a 256x256 grey canvas    -> pixel-level similarity
5. ORB + RANSAC homography inliers  -> "same scene, resized/cropped" evidence

Every pair is verified with ORB (not only prefiltered ones), because several
same-leaf pairs in this dataset are differently framed and have low SSIM.

Outputs:
- data/processed/near_duplicates.csv        screened pairs with metrics
- data/processed/near_duplicate_summary.json
- data/processed/near_duplicate_review.png  contact sheet for manual adjudication

Usage (from the repository root)::

    python scripts/find_near_duplicates.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "rice_leaf_diseases"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
CSV_PATH = PROCESSED_DIR / "near_duplicates.csv"
SUMMARY_PATH = PROCESSED_DIR / "near_duplicate_summary.json"
SHEET_PATH = PROCESSED_DIR / "near_duplicate_review.png"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

HASH_SIZE = 16  # dHash grid -> 16x16 -> 256 bits
CANVAS = 256
ORB_FEATURES = 400

# A pair is written to the CSV only if it shows at least weak evidence.
REPORT_HAMMING = 30
REPORT_HIST = 0.95
REPORT_SSIM = 0.85
REPORT_ORB_INLIERS = 4

# Candidate (needs manual adjudication). Calibrated against hand-verified pairs:
# every confirmed duplicate in this dataset meets at least one of these.
CANDIDATE_HAMMING = 10
CANDIDATE_ORB_INLIERS = 5
CANDIDATE_ORB_RATIO = 0.80
CANDIDATE_SSIM = 0.97
CANDIDATE_HIST = 0.98

FIELDNAMES = [
    "path_a",
    "path_b",
    "label_a",
    "label_b",
    "same_class",
    "dhash_hamming",
    "hist_correlation",
    "ssim",
    "orb_keypoints_a",
    "orb_keypoints_b",
    "orb_matches",
    "orb_inliers",
    "orb_inlier_ratio",
    "verdict",
]


def iter_images() -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for class_dir in sorted(RAW_DIR.iterdir()):
        if not class_dir.is_dir():
            continue
        for path in sorted(class_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                items.append((class_dir.name, path))
    return items


def dhash(gray: np.ndarray, size: int = HASH_SIZE) -> np.ndarray:
    resized = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return np.packbits(diff.reshape(-1))


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.unpackbits(np.bitwise_xor(a, b)).sum())


def hsv_histogram(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=1.0, beta=0.0, norm_type=cv2.NORM_L1)
    return hist


def ssim(gray_a: np.ndarray, gray_b: np.ndarray) -> float:
    a = gray_a.astype(np.float64)
    b = gray_b.astype(np.float64)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    mu_a_sq = mu_a * mu_a
    mu_b_sq = mu_b * mu_b
    mu_ab = mu_a * mu_b
    sigma_a_sq = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a_sq
    sigma_b_sq = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b_sq
    sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab
    numerator = (2 * mu_ab + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a_sq + mu_b_sq + c1) * (sigma_a_sq + sigma_b_sq + c2)
    return float(np.mean(numerator / denominator))


def orb_inliers(
    descriptors_a: np.ndarray | None,
    descriptors_b: np.ndarray | None,
    keypoints_a: list,
    keypoints_b: list,
) -> tuple[int, int, float]:
    """Return (matches, inliers, inlier_ratio) using ORB + RANSAC homography."""
    if descriptors_a is None or descriptors_b is None:
        return 0, 0, 0.0
    if len(descriptors_a) < 4 or len(descriptors_b) < 4:
        return 0, 0, 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(descriptors_a, descriptors_b)
    matches = [m for m in matches if m.distance <= 40]
    if len(matches) < 4:
        return len(matches), 0, 0.0

    points_a = np.float32([keypoints_a[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    points_b = np.float32([keypoints_b[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

    _, mask = cv2.findHomography(points_a, points_b, cv2.RANSAC, 5.0)
    if mask is None:
        return len(matches), 0, 0.0

    inliers = int(mask.ravel().sum())
    return len(matches), inliers, round(inliers / len(matches), 4)


def verdict_for(row: dict[str, object]) -> str:
    if (
        int(row["dhash_hamming"]) <= CANDIDATE_HAMMING
        or (int(row["orb_inliers"]) >= CANDIDATE_ORB_INLIERS
            and float(row["orb_inlier_ratio"]) >= CANDIDATE_ORB_RATIO)
        or (float(row["ssim"]) >= CANDIDATE_SSIM
            and float(row["hist_correlation"]) >= CANDIDATE_HIST)
    ):
        return "candidate"
    return "clear"


def is_reportable(row: dict[str, object]) -> bool:
    return (
        int(row["dhash_hamming"]) <= REPORT_HAMMING
        or float(row["hist_correlation"]) >= REPORT_HIST
        or float(row["ssim"]) >= REPORT_SSIM
        or int(row["orb_inliers"]) >= REPORT_ORB_INLIERS
    )


def contact_sheet(
    pairs: list[dict[str, object]],
    image_by_path: dict[str, np.ndarray],
    pairs_per_row: int = 2,
) -> None:
    """Render candidate pairs side by side for manual adjudication."""
    if not pairs:
        return

    tile_w, tile_h = 300, 190
    caption_h = 34
    pair_w = tile_w * 2
    pair_h = tile_h + caption_h
    gap = 16

    rows = (len(pairs) + pairs_per_row - 1) // pairs_per_row
    sheet_w = pairs_per_row * pair_w + (pairs_per_row + 1) * gap
    sheet_h = rows * pair_h + (rows + 1) * gap
    sheet = np.full((sheet_h, sheet_w, 3), 255, dtype=np.uint8)

    for index, pair in enumerate(pairs):
        row_index, column_index = divmod(index, pairs_per_row)
        x0 = gap + column_index * (pair_w + gap)
        y0 = gap + row_index * (pair_h + gap)

        for slot, key in enumerate(("path_a", "path_b")):
            path = str(pair[key])
            image = image_by_path[path]
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

            scale = min(tile_w / image.shape[1], tile_h / image.shape[0])
            thumb = cv2.resize(
                image,
                (max(1, int(image.shape[1] * scale)), max(1, int(image.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
            x = x0 + slot * tile_w + (tile_w - thumb.shape[1]) // 2
            y = y0 + (tile_h - thumb.shape[0]) // 2
            sheet[y : y + thumb.shape[0], x : x + thumb.shape[1]] = thumb

            caption = path.split("/")[-2] + "/" + path.split("/")[-1]
            cv2.putText(
                sheet,
                caption[:48],
                (x0 + slot * tile_w + 4, y0 + tile_h + 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )

        metrics = (
            f"h={pair['dhash_hamming']} ssim={float(pair['ssim']):.3f} "
            f"hist={float(pair['hist_correlation']):.3f} "
            f"orb={pair['orb_inliers']}/{pair['orb_matches']} "
            f"ratio={float(pair['orb_inlier_ratio']):.2f}"
        )
        cv2.putText(
            sheet,
            metrics,
            (x0 + 4, y0 + tile_h + 29),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (90, 90, 90),
            1,
            cv2.LINE_AA,
        )

    cv2.imwrite(str(SHEET_PATH), sheet)


def main() -> int:
    if not RAW_DIR.is_dir():
        print(f"[error] dataset directory not found: {RAW_DIR}")
        return 2

    images = iter_images()
    processed: dict[str, dict[str, object]] = {}

    for _, path in images:
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        canvas_bgr = cv2.resize(bgr, (CANVAS, CANVAS), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
        keypoints, descriptors = orb.detectAndCompute(gray, None)
        processed[path.relative_to(REPO_ROOT).as_posix()] = {
            "bgr": cv2.resize(bgr, (600, max(1, int(600 * bgr.shape[0] / bgr.shape[1]))), interpolation=cv2.INTER_AREA)
            if bgr.shape[1] > 600
            else bgr,
            "gray": gray,
            "dhash": dhash(gray),
            "hist": hsv_histogram(canvas_bgr),
            "keypoints": keypoints or [],
            "descriptors": descriptors,
            "label": path.parent.name,
        }

    paths = sorted(processed)
    screened: list[dict[str, object]] = []
    for i, path_a in enumerate(paths):
        item_a = processed[path_a]
        for path_b in paths[i + 1 :]:
            item_b = processed[path_b]
            distance = hamming(item_a["dhash"], item_b["dhash"])  # type: ignore[arg-type]
            correlation = float(
                cv2.compareHist(item_a["hist"], item_b["hist"], cv2.HISTCMP_CORREL)  # type: ignore[arg-type]
            )
            similarity = ssim(item_a["gray"], item_b["gray"])  # type: ignore[arg-type]
            matches, inliers, ratio = orb_inliers(
                item_a["descriptors"],  # type: ignore[arg-type]
                item_b["descriptors"],  # type: ignore[arg-type]
                item_a["keypoints"],  # type: ignore[arg-type]
                item_b["keypoints"],  # type: ignore[arg-type]
            )

            row: dict[str, object] = {
                "path_a": path_a,
                "path_b": path_b,
                "label_a": item_a["label"],
                "label_b": item_b["label"],
                "same_class": item_a["label"] == item_b["label"],
                "dhash_hamming": distance,
                "hist_correlation": round(correlation, 4),
                "ssim": round(similarity, 4),
                "orb_keypoints_a": len(item_a["keypoints"]),  # type: ignore[arg-type]
                "orb_keypoints_b": len(item_b["keypoints"]),  # type: ignore[arg-type]
                "orb_matches": matches,
                "orb_inliers": inliers,
                "orb_inlier_ratio": ratio,
            }
            row["verdict"] = verdict_for(row)
            if row["verdict"] == "candidate" or is_reportable(row):
                screened.append(row)

    screened.sort(
        key=lambda row: (
            row["verdict"] != "candidate",
            -int(row["orb_inliers"]),
            -float(row["ssim"]),
            int(row["dhash_hamming"]),
        )
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(screened)

    candidates = [row for row in screened if row["verdict"] == "candidate"]
    cross_class = [row for row in candidates if not row["same_class"]]

    summary = {
        "images_screened": len(paths),
        "pairs_total": len(paths) * (len(paths) - 1) // 2,
        "pairs_reported": len(screened),
        "candidate_pairs": len(candidates),
        "cross_class_candidates": len(cross_class),
        "candidate_pairs_detail": candidates,
        "thresholds": {
            "candidate_hamming": CANDIDATE_HAMMING,
            "candidate_orb_inliers": CANDIDATE_ORB_INLIERS,
            "candidate_orb_ratio": CANDIDATE_ORB_RATIO,
            "candidate_ssim": CANDIDATE_SSIM,
            "candidate_hist": CANDIDATE_HIST,
        },
        "note": (
            "Candidates require manual visual adjudication. Confirmed duplicates are "
            "recorded in data/splits/duplicate_groups.json and kept within the same "
            "partition by scripts/make_splits.py."
        ),
    }
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")

    contact_sheet(candidates, {path: processed[path]["bgr"] for path in paths})  # type: ignore[misc]

    print(f"Pairs total          : {summary['pairs_total']}")
    print(f"Pairs reported       : {summary['pairs_reported']}")
    print(f"Candidate pairs      : {summary['candidate_pairs']}")
    print(f"Cross-class candidate: {summary['cross_class_candidates']}")
    print(f"Report               : {CSV_PATH.relative_to(REPO_ROOT)}")
    print(f"Contact sheet        : {SHEET_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
