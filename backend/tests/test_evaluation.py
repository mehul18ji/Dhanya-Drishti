"""Tests for the Phase 3 M4 evaluation report (reporting only, no retraining).

Pinned here:

1. the module cannot recompute the held-out evaluation — it never imports the
   training helpers that fit, tune or predict, and the report restates the recorded
   held-out block verbatim;
2. baselines are computed from development labels only, deterministically;
3. the development and held-out blocks stay clearly separate.

The artifact-dependent tests read the git-ignored M3 training runs and are skipped
when those runs are absent (a fresh clone has no processed artifacts).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.ml import evaluation
from app.ml.evaluation import (
    DEVELOPMENT_RUN_NAME,
    HELD_OUT_RUN_NAME,
    EXPECTED_DEVELOPMENT_ROWS,
    EXPECTED_HELD_OUT_ROWS,
    build_evaluation_report,
    compute_baselines,
    development_run_dir,
    held_out_run_dir,
    load_development_predictions,
    load_run_report,
    render_markdown,
)
from app.ml.training import CLASS_LABELS, MODEL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_artifacts() -> None:
    development = development_run_dir() / "model_comparison.json"
    predictions = development_run_dir() / "cv_predictions.csv"
    held_out = held_out_run_dir() / "model_comparison.json"
    for path in (development, predictions, held_out):
        if not path.exists():
            pytest.skip(f"processed M3 artifact not present: {path}")


# --------------------------------------------------------------------------- #
# Structural guards: no training, no held-out recomputation
# --------------------------------------------------------------------------- #


def test_module_has_no_training_or_held_out_evaluation_entry_points() -> None:
    source = Path(evaluation.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "evaluate_held_out",
        "fit_final_model",
        "cross_validate_models",
        "build_pipeline",
        "load_feature_matrix",
        "GridSearchCV",
        "sys.path.insert",
    ):
        assert forbidden not in source, f"evaluation.py must not reference {forbidden}"
    assert "app.ml.training import" in source
    assert not hasattr(evaluation, "evaluate_held_out")


def test_package_init_does_not_import_submodules_eagerly() -> None:
    source = (REPO_ROOT / "backend" / "app" / "ml" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "import evaluation" not in source


# --------------------------------------------------------------------------- #
# Baselines (development labels only, deterministic)
# --------------------------------------------------------------------------- #


def _development_like_labels() -> list[str]:
    return [CLASS_LABELS[index % len(CLASS_LABELS)] for index in range(30)] + [
        CLASS_LABELS[0]
    ] * 6


def test_majority_baseline_predicts_the_most_frequent_class() -> None:
    baselines = compute_baselines(_development_like_labels())
    assert baselines.majority_class == CLASS_LABELS[0]
    assert baselines.n == len(_development_like_labels())
    # Majority-class predictor gets every class-0 row right and nothing else.
    assert baselines.majority_metrics["accuracy"] == pytest.approx(16 / 36)
    assert baselines.majority_metrics["macro_recall"] == pytest.approx((1.0 + 0.0 + 0.0) / 3)


def test_stratified_random_baseline_is_deterministic_for_a_fixed_seed() -> None:
    labels = _development_like_labels()
    first = compute_baselines(labels, seed=42)
    second = compute_baselines(labels, seed=42)
    other = compute_baselines(labels, seed=7)

    assert first.random_metrics["macro_f1"] == pytest.approx(
        second.random_metrics["macro_f1"]
    )
    assert first.random_metrics["confusion_matrix"] == second.random_metrics["confusion_matrix"]
    # A different seed is allowed to differ, but must stay a valid 3-class score.
    assert 0.0 <= other.random_metrics["macro_f1"] <= 1.0
    assert sum(sum(row) for row in first.random_metrics["confusion_matrix"]) == first.n


def test_baselines_reject_unknown_labels() -> None:
    with pytest.raises(ValueError):
        compute_baselines(["healthy"])


# --------------------------------------------------------------------------- #
# Report assembly from the frozen M3 artifacts
# --------------------------------------------------------------------------- #


def test_development_predictions_are_the_96_frozen_rows_per_model() -> None:
    _require_artifacts()
    grouped = load_development_predictions(DEVELOPMENT_RUN_NAME)

    assert set(grouped) == set(MODEL_NAMES)
    reference = {item["image_id"] for item in grouped[MODEL_NAMES[0]]}
    assert len(reference) == EXPECTED_DEVELOPMENT_ROWS
    for name in MODEL_NAMES:
        assert len(grouped[name]) == EXPECTED_DEVELOPMENT_ROWS
        assert {item["image_id"] for item in grouped[name]} == reference


def test_held_out_block_is_restated_verbatim_and_never_recomputed() -> None:
    _require_artifacts()
    report = build_evaluation_report(log=lambda _: None)
    recorded = load_run_report(HELD_OUT_RUN_NAME)["held_out"]

    assert report["held_out"] == recorded
    assert report["held_out"]["final"] is True
    assert report["held_out"]["used_for_selection"] is False
    assert report["held_out"]["n"] == EXPECTED_HELD_OUT_ROWS
    # The per-image rows are copied from the stored artifact, never regenerated.
    assert len(report["held_out_predictions"]) == EXPECTED_HELD_OUT_ROWS
    assert report["consistency"]["held_out_predictions_reused_not_regenerated"] is True
    for row in report["held_out_predictions"]:
        assert set(row) == {"image_id", "y_true", "y_pred"}
        assert row["y_true"] in CLASS_LABELS and row["y_pred"] in CLASS_LABELS


def test_report_keeps_development_and_held_out_separate() -> None:
    _require_artifacts()
    report = build_evaluation_report(log=lambda _: None)

    assert report["development"]["rows"] == EXPECTED_DEVELOPMENT_ROWS
    assert set(report["development"]["models"]) == set(MODEL_NAMES)
    for name in MODEL_NAMES:
        block = report["development"]["models"][name]
        assert block["used_held_out_rows"] is False
        assert block["out_of_fold"]["n"] == EXPECTED_DEVELOPMENT_ROWS
    assert report["held_out"]["n"] == EXPECTED_HELD_OUT_ROWS
    assert report["consistency"]["held_out_ids_disjoint_from_development"] is True

    markdown = render_markdown(report)
    assert "## Development — models" in markdown
    assert "## Held-out — single final evaluation" in markdown
    assert markdown.index("## Development — models") < markdown.index(
        "## Held-out — single final evaluation"
    )


def test_development_predictions_reproduce_the_recorded_out_of_fold_metrics() -> None:
    _require_artifacts()
    report = build_evaluation_report(log=lambda _: None)

    matches = report["consistency"]["recomputed_out_of_fold_matches_recorded"]
    assert set(matches) == set(MODEL_NAMES)
    assert all(matches.values()), report["consistency"]["max_metric_difference"]
    for name in MODEL_NAMES:
        assert report["consistency"]["cv_predictions_rows_per_model"][name] == (
            EXPECTED_DEVELOPMENT_ROWS
        )


def test_report_states_the_required_limitations() -> None:
    _require_artifacts()
    report = build_evaluation_report(log=lambda _: None)
    joined = " ".join(report["limitations"]).lower()

    assert "small" in joined and "visually similar" in joined
    assert "healthy" in joined
    assert "severity" in joined
    assert "experimental" in joined


def test_development_run_must_be_the_development_only_run() -> None:
    _require_artifacts()
    with pytest.raises(ValueError):
        # The pre-correction run carries a held-out block, so it is refused as the
        # development source: it would smuggle test results into the development side.
        build_evaluation_report(
            development_run=HELD_OUT_RUN_NAME, log=lambda _: None
        )


def test_written_report_round_trips_as_json_and_markdown(tmp_path: Path) -> None:
    _require_artifacts()
    paths = evaluation.write_evaluation_report(output_dir=tmp_path, log=lambda _: None)

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["report"] == "phase3_m4_evaluation_report"
    assert payload["held_out"]["n"] == EXPECTED_HELD_OUT_ROWS
    assert payload["baselines"]["majority_class"]["metrics"]["n"] == (
        EXPECTED_DEVELOPMENT_ROWS
    )
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "restated, not recomputed" in markdown
    # The report is written under a caller-provided directory only.
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "evaluation_report.json",
        "evaluation_report.md",
    ]


def test_cv_predictions_header_is_validated(tmp_path: Path) -> None:
    header = ["model", "image_id", "y_true"]

    def _write(directory: Path, rows: list[list[str]], fields: list[str]) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "cv_predictions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)
        return directory

    directory = _write(tmp_path / "broken", [], header)
    with pytest.raises(ValueError):
        load_development_predictions(DEVELOPMENT_RUN_NAME, root=directory)
