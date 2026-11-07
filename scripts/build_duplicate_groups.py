"""Encode the manual near-duplicate adjudication as a checked artifact.

Phase 1 deliverable. ``scripts/find_near_duplicates.py`` produces *candidates*;
a human must confirm each one visually. This script records the confirmed
groups (and the rejected false positives) together with the measured evidence,
validates internal consistency, and writes:

    data/splits/duplicate_groups.json

``scripts/make_splits.py`` consumes that file so duplicates can never be split
across train/validation/test partitions (PRD §10).

Every confirmed group was reviewed visually on 2026-11-07. Re-run this script
only after repeating that review; do not add pairs blindly.

Usage (from the repository root)::

    python scripts/build_duplicate_groups.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "rice_leaf_diseases"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SPLITS_DIR = REPO_ROOT / "data" / "splits"
CANDIDATES_CSV = PROCESSED_DIR / "near_duplicates.csv"
OUTPUT_PATH = SPLITS_DIR / "duplicate_groups.json"

# Visual adjudication, 2026-11-07. Folder name -> confirmed same-scene groups.
CONFIRMED_GROUPS: dict[str, list[list[str]]] = {
    "Bacterial leaf blight": [
        ["DSC_0365.JPG", "DSC_0366.jpg"],
        ["DSC_0375.JPG", "DSC_0376.JPG"],
    ],
    "Brown spot": [
        ["DSC_0299.JPG", "DSC_0300.JPG"],
        ["DSC_0302.JPG", "DSC_0303.JPG"],
        ["DSC_0306.JPG", "DSC_0307.JPG"],
    ],
    "Leaf smut": [
        ["DSC_0308.JPG", "DSC_0309.JPG"],
        ["DSC_0312.JPG", "DSC_0313.JPG"],
        ["DSC_0314.JPG", "DSC_0315.jpg"],
        ["DSC_0318.JPG", "DSC_0319.jpg"],
        ["DSC_0321.JPG", "DSC_0322.jpg"],
        ["DSC_0335.JPG", "DSC_0336.jpg"],
        ["DSC_0338.JPG", "DSC_0339.jpg"],
        ["DSC_0504.jpg", "DSC_0512.jpg"],
    ],
}

# DSC_0320 is the same leaf as 0321/0322 (verified by warping 0320 onto 0321:
# the leaf outline and every lesion aligned). Add the transitive member here so
# the group stays complete without listing every pair manually.
EXTRA_GROUP_MEMBERS: dict[tuple[str, ...], list[str]] = {
    ("DSC_0321.JPG", "DSC_0322.jpg"): ["DSC_0320.JPG"],
}

REVIEWED_FALSE_POSITIVES: list[dict[str, str]] = [
    {
        "path_a": "Bacterial leaf blight/DSC_0395.JPG",
        "path_b": "Bacterial leaf blight/DSC_0405.JPG",
        "reason": "Different leaves: the lesion streaks, blade thickness and tip shape differ.",
    },
    {
        "path_a": "Bacterial leaf blight/DSC_0372.JPG",
        "path_b": "Bacterial leaf blight/DSC_0396.JPG",
        "reason": "Different leaves: unrelated lesion layout and blade edge.",
    },
]

MIN_ORB_INLIERS = 5
MIN_ORB_RATIO = 0.80

FOLDER_TO_LABEL = {
    "Bacterial leaf blight": "bacterial_leaf_blight",
    "Brown spot": "brown_spot",
    "Leaf smut": "leaf_smut",
}


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def main() -> int:
    if not CANDIDATES_CSV.exists():
        print(f"[error] run scripts/find_near_duplicates.py first: {CANDIDATES_CSV}")
        return 2

    with CANDIDATES_CSV.open(encoding="utf-8") as handle:
        metrics = {
            pair_key(row["path_a"], row["path_b"]): row for row in csv.DictReader(handle)
        }

    groups: list[dict[str, object]] = []
    seen_paths: dict[str, str] = {}
    class_image_counts: dict[str, int] = {}

    for folder, folder_groups in CONFIRMED_GROUPS.items():
        label = FOLDER_TO_LABEL[folder]
        for index, files in enumerate(folder_groups, start=1):
            files = list(files)
            files.extend(EXTRA_GROUP_MEMBERS.get(tuple(files), []))
            paths = [f"data/raw/rice_leaf_diseases/{folder}/{name}" for name in files]

            for path in paths:
                if path in seen_paths:
                    print(f"[error] {path} appears in groups {seen_paths[path]} and dup-{folder[:4]}-{index}")
                    return 2
                seen_paths[path] = f"dup-{folder[:4]}-{index}"
                if not (REPO_ROOT / path).exists():
                    print(f"[error] missing image: {path}")
                    return 2

            evidence: list[dict[str, object]] = []
            for i, path_a in enumerate(paths):
                for path_b in paths[i + 1 :]:
                    row = metrics.get(pair_key(path_a, path_b))
                    if row is None:
                        print(f"[error] no near-duplicate evidence for {path_a} vs {path_b}")
                        return 2
                    if int(row["orb_inliers"]) < MIN_ORB_INLIERS or float(row["orb_inlier_ratio"]) < MIN_ORB_RATIO:
                        print(
                            f"[error] weak ORB evidence for {path_a} vs {path_b}: "
                            f"inliers={row['orb_inliers']} ratio={row['orb_inlier_ratio']}"
                        )
                        return 2
                    evidence.append(
                        {
                            "path_a": path_a,
                            "path_b": path_b,
                            "dhash_hamming": int(row["dhash_hamming"]),
                            "hist_correlation": float(row["hist_correlation"]),
                            "ssim": float(row["ssim"]),
                            "orb_inliers": int(row["orb_inliers"]),
                            "orb_matches": int(row["orb_matches"]),
                            "orb_inlier_ratio": float(row["orb_inlier_ratio"]),
                        }
                    )

            group_id = f"dup-{label}-{index:02d}"
            groups.append(
                {
                    "group_id": group_id,
                    "label": label,
                    "class_folder": folder,
                    "paths": paths,
                    "evidence": evidence,
                }
            )
            class_image_counts[label] = class_image_counts.get(label, 0) + len(paths)

    groups.sort(key=lambda group: (str(group["label"]), str(group["group_id"])))

    rejected = [
        {
            "path_a": f"data/raw/rice_leaf_diseases/{row['path_a']}",
            "path_b": f"data/raw/rice_leaf_diseases/{row['path_b']}",
            "reason": row["reason"],
        }
        for row in REVIEWED_FALSE_POSITIVES
    ]

    document = {
        "review_version": "v1",
        "reviewed_on": "2026-11-07",
        "reviewer": "AI agent session, visual adjudication of ORB-flagged candidates",
        "method": {
            "generator": "scripts/find_near_duplicates.py",
            "signals": [
                "md5 exact hash",
                "dHash 16x16 (256-bit)",
                "HSV histogram correlation",
                "SSIM on a 256x256 grey canvas",
                "ORB + RANSAC homography inliers",
            ],
            "candidate_rule": (
                "dhash_hamming <= 10 OR (orb_inliers >= 5 AND orb_inlier_ratio >= 0.80) "
                "OR (ssim >= 0.97 AND hist_correlation >= 0.98)"
            ),
            "min_or_inliers_accepted": MIN_ORB_INLIERS,
            "min_orb_ratio_accepted": MIN_ORB_RATIO,
        },
        "confirmed_groups": groups,
        "rejected_candidates": rejected,
        "summary": {
            "groups": len(groups),
            "images_in_groups": sum(len(group["paths"]) for group in groups),
            "by_class": dict(sorted(class_image_counts.items())),
            "confirmed_pair_relationships": sum(
                len(group["paths"]) * (len(group["paths"]) - 1) // 2 for group in groups
            ),
            "rejected_candidates": len(rejected),
        },
        "usage": (
            "scripts/make_splits.py keeps every group entirely inside one partition; "
            "the held-out test set uses only singleton images."
        ),
    }

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("Groups :", document["summary"]["groups"])
    print("Images :", document["summary"]["images_in_groups"], document["summary"]["by_class"])
    print("Pairs  :", document["summary"]["confirmed_pair_relationships"])
    print("Rejected candidates:", document["summary"]["rejected_candidates"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
