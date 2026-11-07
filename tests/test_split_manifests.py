"""Invariant tests for the frozen Phase 1 split manifests.

These tests need only the committed JSON files in ``data/splits/`` — not the raw
images — so they run on any clean checkout.

Run from the repository root::

    python -m pytest tests -q
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPLITS_DIR = REPO_ROOT / "data" / "splits"

EXPECTED_LABELS = {"bacterial_leaf_blight", "brown_spot", "leaf_smut"}
EXPECTED_TOTAL = 120
EXPECTED_TEST = 24
EXPECTED_TEST_PER_CLASS = 8
EXPECTED_CV = 96
EXPECTED_FOLDS = 5


def load(name: str) -> dict:
    with (SPLITS_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_test_set_is_stratified_and_unique() -> None:
    test = load("test.json")
    items = test["items"]

    assert len(items) == EXPECTED_TEST
    assert len({item["path"] for item in items}) == EXPECTED_TEST
    counts = Counter(item["label"] for item in items)
    assert counts == {label: EXPECTED_TEST_PER_CLASS for label in EXPECTED_LABELS}
    assert all(item["md5"] for item in items)


def test_cross_validation_folds_are_disjoint_and_complete() -> None:
    cv = load("cv_folds.json")
    folds = cv["folds"]

    assert cv["n_splits"] == EXPECTED_FOLDS
    assert cv["group_aware"] is True
    assert len(folds) == EXPECTED_FOLDS

    all_validation: list[str] = []
    for fold in folds:
        train = set(fold["train"])
        validation = set(fold["validation"])

        assert train.isdisjoint(validation)
        assert set(fold["train_counts"]) == EXPECTED_LABELS
        assert set(fold["validation_counts"]) == EXPECTED_LABELS

        all_validation.extend(fold["validation"])

    assert len(all_validation) == EXPECTED_CV
    assert len(set(all_validation)) == EXPECTED_CV


def test_test_and_cv_do_not_overlap_and_account_for_all_images() -> None:
    test_paths = {item["path"] for item in load("test.json")["items"]}
    cv = load("cv_folds.json")
    cv_paths = {path for fold in cv["folds"] for path in fold["validation"]}

    assert test_paths.isdisjoint(cv_paths)
    assert len(test_paths) + len(cv_paths) == EXPECTED_TOTAL

    manifest = load("split_manifest.json")
    assert manifest["counts"]["total"] == EXPECTED_TOTAL
    assert manifest["counts"]["test"] == EXPECTED_TEST
    assert manifest["counts"]["cv"] == EXPECTED_CV


def test_confirmed_duplicate_groups_never_cross_partitions() -> None:
    duplicate_document = load("duplicate_groups.json")
    groups = duplicate_document["confirmed_groups"]
    assert groups, "expected at least one confirmed duplicate group"

    path_to_group: dict[str, str] = {}
    for group in groups:
        assert len(group["paths"]) >= 2
        for path in group["paths"]:
            assert path not in path_to_group, f"{path} appears in two groups"
            path_to_group[path] = group["group_id"]

    test_paths = {item["path"] for item in load("test.json")["items"]}
    assert not (test_paths & set(path_to_group)), "test set must contain only singleton images"

    for fold in load("cv_folds.json")["folds"]:
        train_groups = {path_to_group[path] for path in fold["train"] if path in path_to_group}
        validation_groups = {
            path_to_group[path] for path in fold["validation"] if path in path_to_group
        }
        assert train_groups.isdisjoint(validation_groups), (
            f"fold {fold['fold']} splits a confirmed duplicate group"
        )


def test_manifest_hashes_match_split_files() -> None:
    manifest = load("split_manifest.json")
    payload = (SPLITS_DIR / "test.json").read_bytes()
    cv_payload = (SPLITS_DIR / "cv_folds.json").read_bytes()

    import hashlib

    assert manifest["files"]["test_sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["files"]["cv_folds_sha256"] == hashlib.sha256(cv_payload).hexdigest()


def test_manifest_invariants_are_all_true() -> None:
    invariants = load("split_manifest.json")["invariants"]

    assert invariants, "manifest must record its invariants"
    assert all(invariants.values()), invariants
