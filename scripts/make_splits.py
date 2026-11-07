"""Create the frozen, leak-free train/test and cross-validation splits.

Phase 1 deliverable (PRD §10 and §18).

Protocol
--------
- 24-image held-out test set: exactly 8 images per class, chosen only from
  *singleton* images (no confirmed near-duplicate twin), so test metrics are not
  inflated by same-scene pairs.
- Remaining 96 images: stratified 5-fold cross-validation.
- Any confirmed duplicate group (``data/splits/duplicate_groups.json``) stays
  entirely inside one partition: group-aware ``StratifiedGroupKFold`` keeps
  twins in the same fold.
- Fixed seed 42; deterministic file ordering; no timestamps. Re-running the
  script with the same inputs reproduces byte-identical files.

Outputs (all committed, small):
- data/splits/test.json
- data/splits/cv_folds.json
- data/splits/split_manifest.json

Usage (from the repository root)::

    python scripts/make_splits.py
    python scripts/make_splits.py --verify   # check existing files are reproducible
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sklearn.model_selection import StratifiedGroupKFold

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SPLITS_DIR = REPO_ROOT / "data" / "splits"
MANIFEST_CSV = PROCESSED_DIR / "dataset_manifest.csv"
AUDIT_JSON = PROCESSED_DIR / "dataset_audit.json"
DUPLICATE_GROUPS_JSON = SPLITS_DIR / "duplicate_groups.json"

TEST_JSON = SPLITS_DIR / "test.json"
CV_JSON = SPLITS_DIR / "cv_folds.json"
SPLIT_MANIFEST_JSON = SPLITS_DIR / "split_manifest.json"

SPLIT_VERSION = "v1"
SEED = 42
TEST_PER_CLASS = 8
N_SPLITS = 5
EXPECTED_TOTAL = 120


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> list[dict[str, str]]:
    with MANIFEST_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"[error] empty manifest: {MANIFEST_CSV}")
    for row in rows:
        if row["decode_ok"] != "True":
            raise SystemExit(f"[error] undecodable image in manifest: {row['path']}")
    return sorted(rows, key=lambda row: row["path"])


def load_duplicate_groups(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, int], dict[str, object]]:
    """Return (path -> group_id, group_id -> size, raw document)."""
    if not DUPLICATE_GROUPS_JSON.exists():
        raise SystemExit(
            f"[error] missing {DUPLICATE_GROUPS_JSON}. Run "
            "scripts/find_near_duplicates.py then scripts/build_duplicate_groups.py."
        )

    with DUPLICATE_GROUPS_JSON.open(encoding="utf-8") as handle:
        document = json.load(handle)

    known_paths = {row["path"] for row in rows}
    path_to_group: dict[str, str] = {}
    group_sizes: dict[str, int] = {}

    for group in document["confirmed_groups"]:
        group_id = str(group["group_id"])
        members = [str(path) for path in group["paths"]]
        if len(members) < 2:
            raise SystemExit(f"[error] group {group_id} has fewer than two members")
        labels = {str(item["label"]) for item in rows if item["path"] in members}
        if len(labels) != 1:
            raise SystemExit(f"[error] group {group_id} spans multiple classes: {labels}")
        for path in members:
            if path not in known_paths:
                raise SystemExit(f"[error] group {group_id} references an unknown path: {path}")
            if path in path_to_group:
                raise SystemExit(f"[error] {path} belongs to more than one duplicate group")
            path_to_group[path] = group_id
        group_sizes[group_id] = len(members)

    # Singleton images become their own group so group-aware splitting is uniform.
    for row in rows:
        path = row["path"]
        if path not in path_to_group:
            group_id = f"single::{path}"
            path_to_group[path] = group_id
            group_sizes[group_id] = 1

    return path_to_group, group_sizes, document


def select_test(rows: list[dict[str, str]], path_to_group: dict[str, str], group_sizes: dict[str, int]) -> list[str]:
    """Pick exactly TEST_PER_CLASS singletons per class, deterministically."""
    by_class: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_class[row["label"]].append(row["path"])

    test_paths: list[str] = []
    for label in sorted(by_class):
        paths = sorted(by_class[label])
        singletons = [path for path in paths if group_sizes[path_to_group[path]] == 1]

        random.Random(f"{SEED}:test:{label}").shuffle(singletons)
        chosen = singletons[:TEST_PER_CLASS]

        # Safety net: if there were too few singletons, add the smallest groups
        # without exceeding the per-class budget. This dataset has plenty.
        if len(chosen) < TEST_PER_CLASS:
            remaining = [path for path in paths if path not in chosen]
            remaining.sort(key=lambda path: (group_sizes[path_to_group[path]], path))
            for path in remaining:
                if len(chosen) >= TEST_PER_CLASS:
                    break
                group_members = [p for p in paths if path_to_group[p] == path_to_group[path]]
                if len(chosen) + len(group_members) <= TEST_PER_CLASS:
                    chosen.extend(group_members)

        if len(chosen) != TEST_PER_CLASS:
            raise SystemExit(
                f"[error] cannot build a {TEST_PER_CLASS}-image test set for {label} "
                f"without splitting duplicate groups (got {len(chosen)})"
            )
        test_paths.extend(chosen)

    return sorted(test_paths)


def build(
    rows: list[dict[str, str]],
    path_to_group: dict[str, str],
    group_sizes: dict[str, int],
    duplicate_document: dict[str, object],
) -> tuple[dict, dict, dict]:
    test_paths = select_test(rows, path_to_group, group_sizes)
    test_set = set(test_paths)
    cv_rows = [row for row in rows if row["path"] not in test_set]

    if len(test_paths) != TEST_PER_CLASS * 3:
        raise SystemExit(f"[error] expected 24 test images, got {len(test_paths)}")

    paths = [row["path"] for row in cv_rows]
    labels = [row["label"] for row in cv_rows]
    groups = [path_to_group[path] for path in paths]

    splitter = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    folds: list[dict[str, object]] = []
    for fold_index, (train_idx, validation_idx) in enumerate(splitter.split(paths, labels, groups)):
        train_paths = sorted(paths[i] for i in train_idx)
        validation_paths = sorted(paths[i] for i in validation_idx)
        folds.append(
            {
                "fold": fold_index,
                "train": train_paths,
                "validation": validation_paths,
                "train_counts": dict(sorted(Counter(labels[i] for i in train_idx).items())),
                "validation_counts": dict(sorted(Counter(labels[i] for i in validation_idx).items())),
            }
        )

    row_by_path = {row["path"]: row for row in rows}

    test_document = {
        "split_version": SPLIT_VERSION,
        "seed": SEED,
        "test_per_class": TEST_PER_CLASS,
        "counts": dict(sorted(Counter(row_by_path[path]["label"] for path in test_paths).items())),
        "items": [
            {
                "path": path,
                "label": row_by_path[path]["label"],
                "md5": row_by_path[path]["md5"],
            }
            for path in test_paths
        ],
    }

    cv_document = {
        "split_version": SPLIT_VERSION,
        "seed": SEED,
        "n_splits": N_SPLITS,
        "group_aware": True,
        "folds": folds,
    }

    checks = validate(test_paths, folds, rows, path_to_group)

    with AUDIT_JSON.open(encoding="utf-8") as handle:
        audit = json.load(handle)

    split_manifest = {
        "split_version": SPLIT_VERSION,
        "seed": SEED,
        "n_splits": N_SPLITS,
        "test_per_class": TEST_PER_CLASS,
        "dataset_version": audit["dataset_version"],
        "dataset_checksum_sha256": audit["dataset_checksum_sha256"],
        "dataset_manifest_sha256": sha256_file(MANIFEST_CSV),
        "duplicate_groups_sha256": sha256_file(DUPLICATE_GROUPS_JSON),
        "duplicate_groups_applied": len(duplicate_document["confirmed_groups"]),  # type: ignore[arg-type]
        "images_in_duplicate_groups": int(duplicate_document["summary"]["images_in_groups"]),  # type: ignore[index]
        "files": {
            "test": "test.json",
            "cv_folds": "cv_folds.json",
            "test_sha256": sha256_file(TEST_JSON) if TEST_JSON.exists() else None,
            "cv_folds_sha256": sha256_file(CV_JSON) if CV_JSON.exists() else None,
        },
        "counts": {
            "total": len(rows),
            "test": len(test_paths),
            "cv": len(paths),
            "per_class_total": dict(sorted(Counter(row["label"] for row in rows).items())),
            "per_class_test": dict(sorted(Counter(row_by_path[path]["label"] for path in test_paths).items())),
            "per_class_cv": dict(sorted(Counter(labels).items())),
        },
        "invariants": checks,
        "generated_by": "scripts/make_splits.py",
        "generated_on": "2026-11-07",
        "note": (
            "Counts and hashes are deterministic. generated_on is informational only; "
            "re-running with the same inputs produces identical test/cv files."
        ),
    }

    return test_document, cv_document, split_manifest


def validate(
    test_paths: list[str],
    folds: list[dict[str, object]],
    rows: list[dict[str, str]],
    path_to_group: dict[str, str],
) -> dict[str, object]:
    row_by_path = {row["path"]: row for row in rows}
    all_paths = set(row_by_path)
    test_set = set(test_paths)

    # 1. Test set composition.
    test_counts = Counter(row_by_path[path]["label"] for path in test_paths)
    assert len(test_paths) == len(test_set) == 24, "test set must be 24 unique images"
    assert all(count == TEST_PER_CLASS for count in test_counts.values()), f"bad test stratification: {test_counts}"
    assert len(test_counts) == 3, f"all classes must appear in test: {test_counts}"

    # 2. No test image has a duplicate twin anywhere else.
    test_groups = {path_to_group[path] for path in test_paths}
    assert all(
        path_to_group[path] not in test_groups for path in all_paths - test_set
    ), "a test image has a duplicate twin outside the test set"

    # 3. Folds are disjoint, complete and stratified.
    cv_union: set[str] = set()
    for fold in folds:
        train = set(fold["train"])  # type: ignore[arg-type]
        validation = set(fold["validation"])  # type: ignore[arg-type]
        assert not (train & validation), f"fold {fold['fold']} has train/validation overlap"
        assert not (train & test_set) and not (validation & test_set), f"fold {fold['fold']} leaks test images"
        assert set(fold["train_counts"]) == set(fold["validation_counts"]) == {
            "bacterial_leaf_blight",
            "brown_spot",
            "leaf_smut",
        }, f"fold {fold['fold']} misses a class"
        cv_union |= train | validation

        # 4. No duplicate group is split across train/validation.
        train_groups = {path_to_group[path] for path in train}
        validation_groups = {path_to_group[path] for path in validation}
        assert not (train_groups & validation_groups), f"fold {fold['fold']} splits a duplicate group"

    assert len(folds) == N_SPLITS, "wrong number of folds"
    assert cv_union == all_paths - test_set, "folds do not cover all non-test images exactly once"

    return {
        "test_unique": True,
        "test_per_class_ok": True,
        "test_has_no_duplicate_twin": True,
        "folds_disjoint": True,
        "folds_cover_all_non_test_images": True,
        "every_fold_has_all_classes": True,
        "no_duplicate_group_split_across_folds": True,
        "no_test_overlap": True,
        "total_accounted_for": len(test_set) + len(cv_union) == len(all_paths) == EXPECTED_TOTAL,
    }


def dump_json(path: Path, document: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")


def verify() -> int:
    required = [TEST_JSON, CV_JSON, SPLIT_MANIFEST_JSON]
    missing = [path for path in required if not path.exists()]
    if missing:
        print(f"[error] missing split files: {missing}")
        return 2

    rows = load_manifest()
    path_to_group, group_sizes, duplicate_document = load_duplicate_groups(rows)

    with TEST_JSON.open(encoding="utf-8") as handle:
        existing_test = json.load(handle)
    with CV_JSON.open(encoding="utf-8") as handle:
        existing_cv = json.load(handle)

    test_document, cv_document, _ = build(rows, path_to_group, group_sizes, duplicate_document)

    if existing_test != test_document:
        print("[fail] test.json is not reproducible from the current inputs")
        return 1
    if existing_cv != cv_document:
        print("[fail] cv_folds.json is not reproducible from the current inputs")
        return 1

    print("[ok] test.json and cv_folds.json are reproducible (seed and inputs unchanged)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Verify existing splits instead of writing")
    args = parser.parse_args()

    if not MANIFEST_CSV.exists() or not AUDIT_JSON.exists():
        print("[error] run scripts/audit_dataset.py first", file=sys.stderr)
        return 2

    if args.verify:
        return verify()

    rows = load_manifest()
    path_to_group, group_sizes, duplicate_document = load_duplicate_groups(rows)

    # Write test/cv first, then the manifest can hash them.
    test_document, cv_document, _ = build(rows, path_to_group, group_sizes, duplicate_document)
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    dump_json(TEST_JSON, test_document)
    dump_json(CV_JSON, cv_document)

    # Rebuild so the manifest hashes the written files, then write it.
    _, _, split_manifest = build(rows, path_to_group, group_sizes, duplicate_document)
    dump_json(SPLIT_MANIFEST_JSON, split_manifest)

    print(f"Wrote {TEST_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {CV_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {SPLIT_MANIFEST_JSON.relative_to(REPO_ROOT)}")
    print("Test  :", split_manifest["counts"]["test"], split_manifest["counts"]["per_class_test"])
    print("CV    :", split_manifest["counts"]["cv"], split_manifest["counts"]["per_class_cv"])
    print("Folds :", N_SPLITS, "| duplicate images:", split_manifest["images_in_duplicate_groups"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
