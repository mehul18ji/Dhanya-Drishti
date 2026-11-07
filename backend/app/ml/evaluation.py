"""Phase 3 M4 — standalone evaluation report (reporting only).

This module does **not** train, tune, or predict. It reads the frozen Phase 3 M3
artifacts and writes one standalone JSON + Markdown evaluation report:

- development metrics come from the corrected M3 run
  ``data/processed/training_runs/run_20261107T175000Z_svm/model_comparison.json``
  (the run that replays the frozen manifest folds with ``PredefinedSplit``);
- development out-of-fold predictions come from that same run's
  ``cv_predictions.csv`` (288 rows = 96 development images x SVM/RF/KNN);
- the already-consumed held-out result is **restated verbatim** from
  ``data/processed/training_runs/run_20261107T173626Z_svm/model_comparison.json``
  (``held_out`` block). It is never recomputed, predicted on, or tuned against;
- honest baselines (majority class, deterministic stratified random) are computed
  from **development-only** labels and predictions.

Nothing here touches ``data/features``, the raw dataset, the split manifests, the
selected SVM configuration, the feature schema ``1.0.0``, or any Phase 2 code.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from app.ml.training import CLASS_LABELS, METRIC_KEYS, MODEL_NAMES, compute_metrics

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_RUN_ROOT = REPO_ROOT / "data" / "processed" / "training_runs"

#: Corrected M3 run: frozen manifest folds, development-only (no held-out block).
DEVELOPMENT_RUN_NAME = "run_20261107T175000Z_svm"
#: The run that consumed the 24 held-out rows exactly once. Read-only here.
HELD_OUT_RUN_NAME = "run_20261107T173626Z_svm"

SEED = 42
EXPECTED_DEVELOPMENT_ROWS = 96
EXPECTED_HELD_OUT_ROWS = 24
PREDICTION_FIELDS = ("model", "image_id", "y_true", "y_pred")
METRIC_TOLERANCE = 1e-9

LIMITATIONS: tuple[str, ...] = (
    "96 development images and 24 held-out images from one small, visually similar "
    "3-class dataset. Scores are optimistically biased by dataset size and "
    "near-duplicate similarity and are not a real-world accuracy claim.",
    "There is no healthy-leaf class. The system predicts only Bacterial Leaf Blight, "
    "Brown Spot and Leaf Smut and must never be described as a diseased/healthy "
    "classifier.",
    "Severity is an experimental lesion-area estimate and is always shown with its "
    "disclaimer; nothing in this report validates severity clinically.",
    "The selected SVM pipeline exposes no calibrated probabilities, so confidence "
    "handling remains a Phase 4 decision.",
    "Baselines and models are scored on the same development labels; they are "
    "reference points, not independent replications.",
    "The single 24-image held-out evaluation is restated, not repeated: its sampling "
    "noise is roughly +/-0.05-0.08 macro F1 and is stated rather than explained away.",
)


def development_run_dir(run_name: str = DEVELOPMENT_RUN_NAME) -> Path:
    return TRAINING_RUN_ROOT / run_name


def held_out_run_dir(run_name: str = HELD_OUT_RUN_NAME) -> Path:
    return TRAINING_RUN_ROOT / run_name


def load_run_report(run_name: str, *, root: Path | None = None) -> dict[str, Any]:
    """Load one M3 ``model_comparison.json`` without modifying it."""
    directory = Path(root) if root is not None else development_run_dir(run_name)
    path = directory / "model_comparison.json"
    if not path.exists():
        raise FileNotFoundError(f"missing M3 run report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_development_predictions(
    run_name: str = DEVELOPMENT_RUN_NAME, *, root: Path | None = None
) -> dict[str, list[dict[str, str]]]:
    """Read the development out-of-fold predictions written by the M3 run.

    Returns ``{model: [{image_id, y_true, y_pred}, ...]}``. Every model must have
    exactly the 96 development rows with the same image ids.
    """
    directory = Path(root) if root is not None else development_run_dir(run_name)
    path = directory / "cv_predictions.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"missing development out-of-fold predictions: {path}"
        )

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        rows = list(reader)

    if header != PREDICTION_FIELDS:
        raise ValueError(
            f"{path.name} header is {header!r}, expected {PREDICTION_FIELDS!r}"
        )

    grouped: dict[str, list[dict[str, str]]] = {name: [] for name in MODEL_NAMES}
    for row in rows:
        model = row["model"]
        if model not in grouped:
            raise ValueError(f"{path.name} has an unknown model {model!r}")
        grouped[model].append(
            {
                "image_id": row["image_id"],
                "y_true": row["y_true"],
                "y_pred": row["y_pred"],
            }
        )

    reference_ids: set[str] | None = None
    for model in MODEL_NAMES:
        predictions = grouped[model]
        if len(predictions) != EXPECTED_DEVELOPMENT_ROWS:
            raise ValueError(
                f"{path.name} has {len(predictions)} rows for {model!r}, expected "
                f"{EXPECTED_DEVELOPMENT_ROWS}"
            )
        ids = [item["image_id"] for item in predictions]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{path.name} repeats an image id for {model!r}")
        if reference_ids is None:
            reference_ids = set(ids)
        elif set(ids) != reference_ids:
            raise ValueError(
                f"{path.name} development image ids differ between models"
            )
        for item in predictions:
            if item["y_true"] not in CLASS_LABELS:
                raise ValueError(
                    f"{path.name} has an unknown label {item['y_true']!r}"
                )
            if item["y_pred"] not in CLASS_LABELS:
                raise ValueError(
                    f"{path.name} has an unknown prediction {item['y_pred']!r}"
                )
    return grouped


def load_held_out_predictions(
    run_name: str = HELD_OUT_RUN_NAME, *, root: Path | None = None
) -> list[dict[str, str]]:
    """The stored held-out predictions, restated (never produced again).

    These were written by the single held-out evaluation that already happened. This
    reader only copies the recorded rows so the report can show them; it never fits a
    model and never predicts.
    """
    directory = Path(root) if root is not None else held_out_run_dir(run_name)
    path = directory / "held_out_predictions.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            {"image_id": row["image_id"], "y_true": row["y_true"], "y_pred": row["y_pred"]}
            for row in csv.DictReader(handle)
        ]
    for row in rows:
        if row["y_true"] not in CLASS_LABELS or row["y_pred"] not in CLASS_LABELS:
            raise ValueError(f"{path.name} contains a label outside the three classes")
    return rows


def load_held_out_ids(
    run_name: str = HELD_OUT_RUN_NAME, *, root: Path | None = None
) -> tuple[str, ...]:
    """Image ids of the consumed held-out set, used only for a disjointness check."""
    return tuple(
        row["image_id"] for row in load_held_out_predictions(run_name, root=root)
    )


# --------------------------------------------------------------------------- #
# Honest baselines (development labels only)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Baselines:
    majority_class: str
    majority_metrics: dict[str, Any]
    random_metrics: dict[str, Any]
    label_distribution: dict[str, int]
    seed: int
    n: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "majority_class": {
                "class": self.majority_class,
                "n": self.n,
                "metrics": self.majority_metrics,
            },
            "stratified_random": {
                "seed": self.seed,
                "class_prior": {
                    label: count / self.n
                    for label, count in self.label_distribution.items()
                },
                "n": self.n,
                "metrics": self.random_metrics,
            },
            "label_distribution": dict(self.label_distribution),
        }


def compute_baselines(
    labels: Sequence[str], *, seed: int = SEED
) -> Baselines:
    """Majority-class and deterministic stratified-random baselines.

    Both are scored against the development labels only. The random baseline draws
    predictions from the development class prior with a fixed seed, so it is exactly
    reproducible and never sees a held-out row.
    """
    distribution = {label: 0 for label in CLASS_LABELS}
    for label in labels:
        if label not in distribution:
            raise ValueError(f"unknown label {label!r} in baseline labels")
        distribution[label] += 1
    total = int(sum(distribution.values()))
    if total == 0:
        raise ValueError("baselines need at least one development label")

    majority_class = max(
        CLASS_LABELS, key=lambda label: (distribution[label], -CLASS_LABELS.index(label))
    )
    y_true = np.asarray(list(labels), dtype=object)

    majority_pred = np.full(total, majority_class, dtype=object)
    majority_metrics = compute_metrics(y_true, majority_pred)

    prior = np.asarray([distribution[label] for label in CLASS_LABELS], dtype=np.float64)
    prior = prior / prior.sum()
    rng = np.random.default_rng(seed)
    random_pred = rng.choice(
        np.asarray(CLASS_LABELS, dtype=object), size=total, p=prior
    )
    random_metrics = compute_metrics(y_true, np.asarray(random_pred, dtype=object))

    return Baselines(
        majority_class=majority_class,
        majority_metrics=majority_metrics,
        random_metrics=random_metrics,
        label_distribution=distribution,
        seed=seed,
        n=total,
    )


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #


def _recomputed_out_of_fold(
    predictions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    y_true = np.asarray([item["y_true"] for item in predictions], dtype=object)
    y_pred = np.asarray([item["y_pred"] for item in predictions], dtype=object)
    return compute_metrics(y_true, y_pred)


def _metrics_agree(recorded: Mapping[str, Any], recomputed: Mapping[str, Any]) -> float:
    worst = 0.0
    for key in METRIC_KEYS:
        difference = abs(float(recorded[key]) - float(recomputed[key]))
        worst = max(worst, difference)
    return worst


def build_evaluation_report(
    *,
    development_run: str = DEVELOPMENT_RUN_NAME,
    held_out_run: str = HELD_OUT_RUN_NAME,
    seed: int = SEED,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Assemble the standalone evaluation report from frozen M3 artifacts."""
    development_report = load_run_report(development_run)
    if development_report.get("held_out_status") != "not_evaluated_development_only":
        raise ValueError(
            "the development run must be the development-only M3 run "
            f"(held_out_status={development_report.get('held_out_status')!r})"
        )
    if development_report.get("held_out") is not None:
        raise ValueError("the development run unexpectedly carries held-out results")

    comparison = development_report.get("comparison") or {}
    missing = [name for name in MODEL_NAMES if name not in comparison]
    if missing:
        raise ValueError(f"development run is missing models: {missing}")

    development_predictions = load_development_predictions(development_run)
    log(
        "development run   : "
        f"{development_run} ({EXPECTED_DEVELOPMENT_ROWS} rows x {len(MODEL_NAMES)} models)"
    )

    held_out_report = load_run_report(held_out_run)
    held_out_block = held_out_report.get("held_out")
    if held_out_block is None:
        raise ValueError(f"held-out run {held_out_run!r} has no held_out block")
    if held_out_block.get("final") is not True:
        raise ValueError("recorded held-out block is not marked final")
    if held_out_block.get("used_for_selection") is not False:
        raise ValueError("recorded held-out block claims to have been used for selection")
    if int(held_out_block.get("n", 0)) != EXPECTED_HELD_OUT_ROWS:
        raise ValueError(
            f"recorded held-out block has n={held_out_block.get('n')!r}, expected "
            f"{EXPECTED_HELD_OUT_ROWS}"
        )
    held_out_predictions = load_held_out_predictions(held_out_run)
    if len(held_out_predictions) != EXPECTED_HELD_OUT_ROWS:
        raise ValueError(
            f"held-out run stores {len(held_out_predictions)} predictions, expected "
            f"{EXPECTED_HELD_OUT_ROWS}"
        )
    log(f"held-out source   : {held_out_run} (restated verbatim, not recomputed)")

    # Development-only baseline inputs.
    development_labels = [item["y_true"] for item in development_predictions[MODEL_NAMES[0]]]
    baselines = compute_baselines(development_labels, seed=seed)
    log(f"baselines         : {baselines.n} development labels, seed {seed}")

    consistency: dict[str, Any] = {
        "cv_predictions_rows_per_model": {
            name: len(development_predictions[name]) for name in MODEL_NAMES
        },
        "recomputed_out_of_fold_matches_recorded": {},
        "max_metric_difference": {},
    }
    for name in MODEL_NAMES:
        recomputed = _recomputed_out_of_fold(development_predictions[name])
        recorded = comparison[name]["out_of_fold"]["metrics"]
        worst = _metrics_agree(recorded, recomputed)
        consistency["recomputed_out_of_fold_matches_recorded"][name] = (
            worst <= METRIC_TOLERANCE
        )
        consistency["max_metric_difference"][name] = worst

    held_out_ids = set(load_held_out_ids(held_out_run))
    development_ids = {item["image_id"] for item in development_predictions[MODEL_NAMES[0]]}
    overlap = held_out_ids & development_ids
    consistency["held_out_ids_disjoint_from_development"] = not overlap
    consistency["held_out_ids_checked"] = len(held_out_ids)
    consistency["held_out_prediction_rows"] = len(held_out_predictions)
    consistency["held_out_predictions_reused_not_regenerated"] = True
    if overlap:
        raise ValueError(
            f"development predictions contain held-out images: {sorted(overlap)[:3]}"
        )

    models_block: dict[str, Any] = {}
    for name in MODEL_NAMES:
        block = comparison[name]
        models_block[name] = {
            "cv": {key: block["cv"][key] for key in METRIC_KEYS},
            "cv_macro_f1_mean": block["cv"]["macro_f1"]["mean"],
            "cv_macro_f1_std": block["cv"]["macro_f1"]["std"],
            "out_of_fold": {
                "metrics": {key: block["out_of_fold"]["metrics"][key] for key in METRIC_KEYS},
                "confusion_matrix": block["out_of_fold"]["confusion_matrix"],
                "per_class": dict(block["out_of_fold"]["per_class"]),
                "labels": list(block["out_of_fold"]["labels"]),
                "n": block["out_of_fold"]["n"],
            },
            "used_held_out_rows": False,
        }

    report: dict[str, Any] = {
        "report": "phase3_m4_evaluation_report",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feature_set_version": development_report.get("feature_set_version"),
        "provenance": dict(development_report.get("provenance") or {}),
        "configs": {
            "segmentation_config_version": development_report.get(
                "segmentation_config_version"
            ),
            "segmentation_config_sha256": development_report.get(
                "segmentation_config_sha256"
            ),
            "quality_config_version": development_report.get("quality_config_version"),
            "quality_config_sha256": development_report.get("quality_config_sha256"),
        },
        "development": {
            "source_run": development_run,
            "source_files": ["model_comparison.json", "cv_predictions.csv"],
            "rows": EXPECTED_DEVELOPMENT_ROWS,
            "cv_protocol": dict(development_report.get("cv_protocol") or {}),
            "selection_metric": "cv_macro_f1_mean",
            "models": models_block,
            "selected": {
                "model": (development_report.get("winner") or {}).get("model"),
                "cv_macro_f1_mean": (development_report.get("winner") or {}).get(
                    "cv_macro_f1_mean"
                ),
                "cv_macro_f1_std": (development_report.get("winner") or {}).get(
                    "cv_macro_f1_std"
                ),
                "best_params": dict((development_report.get("winner") or {}).get("best_params") or {}),
            },
        },
        "baselines": baselines.as_dict(),
        "held_out": dict(held_out_block),
        "held_out_predictions": held_out_predictions,
        "held_out_source": {
            "run": held_out_run,
            "file": "model_comparison.json",
            "note": (
                "Evaluated exactly once after selection on the pre-correction run whose "
                "fitted pipeline is identical to the corrected one. Restated verbatim; "
                "not recomputed, not tuned against, not overwritten by this report."
            ),
        },
        "consistency": consistency,
        "limitations": list(LIMITATIONS),
        "caveat": development_report.get("caveat", ""),
    }
    return report


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def _num(value: Any, places: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.{places}f}" if math.isfinite(number) else "n/a"


def _confusion_table(block: Mapping[str, Any]) -> list[str]:
    labels = list(block["labels"])
    lines = ["| true \\ predicted | " + " | ".join(labels) + " |"]
    lines.append("|---|" + "---:|" * len(labels))
    matrix = block["confusion_matrix"]
    for row_index, label in enumerate(labels):
        cells = [str(matrix[row_index][column]) for column in range(len(labels))]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def _metric_row(name: str, metrics: Mapping[str, Any]) -> str:
    accuracy = _num(metrics.get("accuracy"))
    balanced = _num(metrics.get("balanced_accuracy"))
    precision = _num(metrics.get("macro_precision"))
    recall = _num(metrics.get("macro_recall"))
    macro_f1 = _num(metrics.get("macro_f1"))
    return (
        f"| {name} | {accuracy} | {balanced} | {precision} | {recall} | {macro_f1} |"
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = []
    version = report.get("feature_set_version")
    lines.append(f"# Model evaluation — feature set v{version}")
    lines.append("")
    generated = report.get("generated_at")
    source = (report.get("development") or {}).get("source_run")
    lines.append(f"Generated `{generated}` | development run `{source}`")
    lines.append("")
    lines.append(
        "This report restates the frozen Phase 3 M3 results and adds honest baselines. "
        "It trains nothing, predicts nothing, and does not recompute the held-out "
        "evaluation."
    )
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    provenance = report.get("provenance") or {}
    configs = report.get("configs") or {}
    lines.append(f"- feature set version: **{version}**")
    lines.append(
        f"- segmentation config: `{configs.get('segmentation_config_version')}` "
        f"(sha256 `{str(configs.get('segmentation_config_sha256'))[:12]}...`)"
    )
    lines.append(
        f"- quality config: `{configs.get('quality_config_version')}` "
        f"(sha256 `{str(configs.get('quality_config_sha256'))[:12]}...`)"
    )
    lines.append(
        f"- split protocol: **{provenance.get('split_version')}** (seed {provenance.get('seed')})"
    )
    lines.append(f"- dataset version: `{provenance.get('dataset_version')}`")
    lines.append("")

    lines.append("## Baseline reference points (development only)")
    lines.append("")
    baselines = report.get("baselines") or {}
    lines.append(
        "- **majority class**: always predict the most frequent development class."
    )
    lines.append(
        "- **stratified random**: deterministic draw from the development class prior "
        "with a fixed seed."
    )
    lines.append("")
    lines.append(
        "| baseline | accuracy | balanced acc. | macro precision | macro recall | macro F1 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    majority = baselines.get("majority_class") or {}
    random_block = baselines.get("stratified_random") or {}
    lines.append(_metric_row(f"majority ({majority.get('class')})", majority.get("metrics") or {}))
    lines.append(
        _metric_row(
            f"stratified random (seed {random_block.get('seed')})",
            random_block.get("metrics") or {},
        )
    )
    lines.append("")
    distribution = baselines.get("label_distribution") or {}
    if distribution:
        pairs = ", ".join(f"`{label}` {count}" for label, count in sorted(distribution.items()))
        lines.append(f"Development label distribution: {pairs}")
        lines.append("")

    lines.append("## Development — models (frozen manifest folds)")
    lines.append("")
    development = report.get("development") or {}
    models = development.get("models") or {}
    lines.append(
        "| model | CV macro F1 | std | CV accuracy | CV balanced acc. | OOF macro F1 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for name in MODEL_NAMES:
        block = models.get(name) or {}
        cv = block.get("cv") or {}
        out_of_fold = block.get("out_of_fold") or {}
        lines.append(
            "| "
            + name
            + " | "
            + _num((cv.get("macro_f1") or {}).get("mean"))
            + " | "
            + _num((cv.get("macro_f1") or {}).get("std"))
            + " | "
            + _num((cv.get("accuracy") or {}).get("mean"))
            + " | "
            + _num((cv.get("balanced_accuracy") or {}).get("mean"))
            + " | "
            + _num((out_of_fold.get("metrics") or {}).get("macro_f1"))
            + " |"
        )
    lines.append("")

    selected = development.get("selected") or {}
    lines.append(
        f"Selected model: **{selected.get('model')}** by mean CV macro F1 "
        f"({_num(selected.get('cv_macro_f1_mean'))} ± {_num(selected.get('cv_macro_f1_std'))}); "
        f"hyperparameters `{json.dumps(selected.get('best_params') or {})}`."
    )
    lines.append("")

    out_of_fold_labels = list(
        ((models.get(MODEL_NAMES[0]) or {}).get("out_of_fold") or {}).get("labels") or []
    )
    if out_of_fold_labels:
        lines.append("### Out-of-fold confusion matrices (development)")
        lines.append("")
        for name in MODEL_NAMES:
            block = (models.get(name) or {}).get("out_of_fold") or {}
            lines.append(f"**{name}**")
            lines.append("")
            lines.extend(_confusion_table(block))
            lines.append("")

    lines.append("## Held-out — single final evaluation (restated, not recomputed)")
    lines.append("")
    held_out = report.get("held_out") or {}
    held_out_source = report.get("held_out_source") or {}
    if not held_out:
        lines.append("No held-out result is recorded for this report.")
        lines.append("")
    else:
        lines.append(
            f"Source: `{held_out_source.get('run')}` — {held_out_source.get('note')}"
        )
        lines.append("")
        lines.append(
            "| accuracy | balanced acc. | macro precision | macro recall | macro F1 | n |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|")
        held_metrics = held_out.get("metrics") or {}
        lines.append(
            "| "
            + _num(held_metrics.get("accuracy"))
            + " | "
            + _num(held_metrics.get("balanced_accuracy"))
            + " | "
            + _num(held_metrics.get("macro_precision"))
            + " | "
            + _num(held_metrics.get("macro_recall"))
            + " | "
            + _num(held_metrics.get("macro_f1"))
            + " | "
            + str(held_out.get("n"))
            + " |"
        )
        lines.append("")
        lines.extend(_confusion_table(held_out))
        lines.append("")
        held_out_predictions = report.get("held_out_predictions") or []
        if held_out_predictions:
            lines.append("Per-image predictions (stored rows, not regenerated):")
            lines.append("")
            lines.append("| image | true | predicted | correct |")
            lines.append("|---|---|---|:---:|")
            for row in held_out_predictions:
                correct = "yes" if row["y_true"] == row["y_pred"] else "no"
                lines.append(
                    f"| {row['image_id']} | {row['y_true']} | {row['y_pred']} | {correct} |"
                )
            lines.append("")
        per_class = held_out.get("per_class") or {}
        if per_class:
            lines.append("| class | precision | recall | F1 | support |")
            lines.append("|---|---:|---:|---:|---:|")
            for label in held_out.get("labels") or []:
                values = per_class.get(label) or {}
                lines.append(
                    "| "
                    + label
                    + " | "
                    + _num(values.get("precision"))
                    + " | "
                    + _num(values.get("recall"))
                    + " | "
                    + _num(values.get("f1"))
                    + " | "
                    + str(values.get("support"))
                    + " |"
                )
            lines.append("")

    lines.append("## Verification")
    lines.append("")
    consistency = report.get("consistency") or {}
    matches = consistency.get("recomputed_out_of_fold_matches_recorded") or {}
    checked = ", ".join(
        f"{name}={'yes' if matches.get(name) else 'no'}" for name in MODEL_NAMES
    )
    lines.append(f"- development predictions re-scored against recorded metrics: {checked}")
    lines.append(
        "- held-out image ids overlap development ids: "
        + ("no" if consistency.get("held_out_ids_disjoint_from_development") else "yes")
    )
    lines.append("- held-out results recomputed by this report: no")
    lines.append(
        "- held-out prediction rows restated from the stored artifact: "
        + str(consistency.get("held_out_prediction_rows"))
    )
    lines.append("- models trained or tuned by this report: no")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for item in report.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_evaluation_report(
    *,
    development_run: str = DEVELOPMENT_RUN_NAME,
    held_out_run: str = HELD_OUT_RUN_NAME,
    output_dir: Path | None = None,
    seed: int = SEED,
    log: Callable[[str], None] = print,
) -> dict[str, Path]:
    """Write ``evaluation_report.json`` and ``evaluation_report.md``."""
    report = build_evaluation_report(
        development_run=development_run,
        held_out_run=held_out_run,
        seed=seed,
        log=log,
    )
    directory = Path(output_dir) if output_dir is not None else TRAINING_RUN_ROOT / "evaluation"
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "evaluation_report.json"
    markdown_path = directory / "evaluation_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    log(f"wrote             : {json_path}")
    log(f"wrote             : {markdown_path}")
    return {"json": json_path, "markdown": markdown_path}


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-run", default=DEVELOPMENT_RUN_NAME)
    parser.add_argument("--held-out-run", default=HELD_OUT_RUN_NAME)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(list(argv) if argv is not None else None)

    write_evaluation_report(
        development_run=args.development_run,
        held_out_run=args.held_out_run,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
