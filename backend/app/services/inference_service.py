"""Artifact-backed inference service (Phase 4 M1).

One entry point that turns a Phase 3 feature vector into a disease label using the
committed production bundle in ``backend/app/artifacts/production/``. Nothing here
trains, fits, recalibrates or predicts on the held-out rows: the pipeline is loaded
from disk once per process and only ever used for inference.

What is verified at load time (a broken bundle must fail loudly, never predict):

1. every file listed in ``model_manifest.json`` exists and its SHA-256 matches;
2. the packaged feature schema names/order/version match
   :mod:`app.vision.feature_extraction` exactly, and its class list matches the
   manifest and the pipeline's own ``classes_``;
3. the pinned ``seg-v2`` / ``quality-v1`` version and SHA-256 match both the
   manifest and the live YAML configs, so features extracted now are comparable
   to the features the model was fitted on;
4. the pipeline is the expected ``imputer -> scaler -> SVC`` chain expecting the
   50 schema features.

Score semantics (PRD §11): the bundle's SVC exposes ``decision_function``, **not**
calibrated probabilities, so the service reports ``decision_margin`` values and a
``margin`` between the best and second-best class. It never emits a confidence
percentage and never claims a probability.

Loading once: :func:`get_inference_service` is a process-wide, thread-safe cache.
It is the hook the application lifespan calls at startup; it is never called from a
request handler, so no request ever pays the load cost or sees a half-loaded model.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import joblib
import numpy as np

from app.core.config import get_settings
from app.vision.config import load_quality_config, load_segmentation_config
from app.vision.feature_extraction import (
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    LESION_DEPENDENT_FEATURES,
    FeatureExtractionResult,
)

#: Reported score semantics. The SVC has no calibrated probabilities.
SCORE_KIND: Final[str] = "decision_margin"
SCORE_NOTE: Final[str] = (
    "decision_function values (one-vs-rest margins), not probabilities. A larger "
    "value means the model preferred that class; it is not a confidence percentage."
)

MODEL_FILE: Final[str] = "model_pipeline.joblib"
SCHEMA_FILE: Final[str] = "feature_schema.json"
CONFIG_FILE: Final[str] = "segmentation_config.json"
MANIFEST_FILE: Final[str] = "model_manifest.json"
PREPROCESSING_FILE: Final[str] = "preprocessing.json"
EVALUATION_FILE: Final[str] = "evaluation_report.json"

EXPECTED_PIPELINE_STEPS: Final[tuple[str, ...]] = ("imputer", "scaler", "model")
EXPECTED_FEATURE_COUNT: Final[int] = 50


class InferenceError(RuntimeError):
    """Base class for inference-service failures."""


class BundleIntegrityError(InferenceError):
    """A bundle file is missing or does not match its recorded SHA-256."""


class SchemaMismatchError(InferenceError):
    """The packaged feature schema is not the active extractor's schema."""


class ConfigMismatchError(InferenceError):
    """The bundle's Phase 2 configuration is not the active configuration."""


class UnusableFeatureVectorError(InferenceError):
    """The feature result carries no vector (a rejected image)."""


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _default_bundle_dir() -> Path:
    settings = get_settings()
    return settings.resolve_path(settings.model_dir)


@dataclass(frozen=True)
class LoadedBundle:
    """The verified production bundle, loaded exactly as exported."""

    bundle_dir: Path
    pipeline: Any
    manifest: dict[str, Any]
    schema: dict[str, Any]
    config: dict[str, Any]
    classes: tuple[str, ...]
    feature_names: tuple[str, ...]

    @property
    def model_name(self) -> str:
        return str(self.manifest["model"]["name"])

    @property
    def model_version(self) -> str:
        return f"{self.model_name}-v{self.manifest.get('bundle_version', '0')}"

    @property
    def feature_set_version(self) -> str:
        return str(self.schema["feature_set_version"])

    @property
    def segmentation_config_version(self) -> str:
        return str(self.config["segmentation_config_version"])

    @property
    def segmentation_config_sha256(self) -> str:
        return str(self.config["segmentation_config_sha256"])

    @property
    def quality_config_version(self) -> str:
        return str(self.config["quality_config_version"])

    @property
    def quality_config_sha256(self) -> str:
        return str(self.config["quality_config_sha256"])

    @property
    def produces_probabilities(self) -> bool:
        return bool(self.manifest["model"].get("calibrated_probabilities", False))


@dataclass(frozen=True)
class PredictionOutcome:
    """One prediction plus everything needed to describe it honestly.

    ``decision_scores`` are one-vs-rest decision margins, **not** probabilities.
    """

    label: str
    decision_scores: dict[str, float]
    margin: float
    ranking: tuple[str, ...]
    model_name: str
    model_version: str
    feature_set_version: str
    segmentation_config_version: str
    quality_config_version: str
    status: str
    lesion_reliable: bool
    lesion_area_percentage: float | None
    warnings: tuple[str, ...] = ()
    missing_features: tuple[str, ...] = ()
    score_kind: str = SCORE_KIND
    score_note: str = SCORE_NOTE

    @property
    def is_margin_based(self) -> bool:
        return self.score_kind == SCORE_KIND

    def as_dict(self) -> dict[str, Any]:
        """Flat, JSON-safe view for later response models."""
        return {
            "label": self.label,
            "decision_scores": dict(self.decision_scores),
            "margin": self.margin,
            "ranking": list(self.ranking),
            "score_kind": self.score_kind,
            "score_note": self.score_note,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "feature_set_version": self.feature_set_version,
            "segmentation_config_version": self.segmentation_config_version,
            "quality_config_version": self.quality_config_version,
            "status": self.status,
            "lesion_reliable": self.lesion_reliable,
            "lesion_area_percentage": self.lesion_area_percentage,
            "warnings": list(self.warnings),
            "missing_features": list(self.missing_features),
        }


# --------------------------------------------------------------------------- #
# Bundle loading and verification
# --------------------------------------------------------------------------- #


def _read_json(path: Path, *, error: type[InferenceError]) -> dict[str, Any]:
    if not path.exists():
        raise error(f"missing bundle file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise error(f"{path.name} is not valid JSON: {exc}") from exc


def verify_artifact_hashes(bundle_dir: Path, manifest: dict[str, Any]) -> None:
    """Every artifact listed in the manifest must match its recorded SHA-256."""
    artifacts = manifest.get("artifacts") or {}
    if not artifacts:
        raise BundleIntegrityError("manifest lists no artifacts")

    for name, record in artifacts.items():
        path = Path(bundle_dir) / name
        if not path.exists():
            raise BundleIntegrityError(f"missing artifact: {name}")
        expected = record.get("sha256")
        if not expected:
            raise BundleIntegrityError(f"manifest has no sha256 for {name}")
        actual = _sha256_of(path)
        if actual != expected:
            raise BundleIntegrityError(
                f"{name} does not match its manifest hash "
                f"(expected {expected[:12]}..., got {actual[:12]}...)"
            )
        recorded_bytes = record.get("bytes")
        if recorded_bytes is not None and int(recorded_bytes) != path.stat().st_size:
            raise BundleIntegrityError(f"{name} size does not match the manifest")


def verify_schema(schema: dict[str, Any], manifest: dict[str, Any]) -> None:
    """The packaged schema must be exactly the active extractor's schema."""
    names = tuple(schema.get("feature_names") or ())
    if names != FEATURE_NAMES:
        raise SchemaMismatchError(
            "packaged feature names/order do not match the active extractor; "
            "re-export the bundle"
        )
    if schema.get("feature_set_version") != FEATURE_SET_VERSION:
        raise SchemaMismatchError(
            f"packaged feature set {schema.get('feature_set_version')!r} is not the "
            f"active {FEATURE_SET_VERSION!r}"
        )
    if int(schema.get("feature_count", 0)) != EXPECTED_FEATURE_COUNT:
        raise SchemaMismatchError(
            f"packaged feature count {schema.get('feature_count')!r} is not "
            f"{EXPECTED_FEATURE_COUNT}"
        )
    if tuple(schema.get("lesion_dependent_features") or ()) != LESION_DEPENDENT_FEATURES:
        raise SchemaMismatchError("packaged lesion-dependent feature list changed")

    manifest_features = manifest.get("features") or {}
    if manifest_features.get("feature_set_version") != schema.get("feature_set_version"):
        raise SchemaMismatchError(
            "manifest and schema disagree about the feature set version"
        )
    if int(manifest_features.get("feature_count", 0)) != EXPECTED_FEATURE_COUNT:
        raise SchemaMismatchError("manifest feature count is not the active schema")

    schema_classes = tuple(schema.get("classes") or ())
    manifest_classes = tuple((manifest.get("model") or {}).get("classes") or ())
    if schema_classes != manifest_classes or not schema_classes:
        raise SchemaMismatchError("schema and manifest disagree about the classes")


def verify_config(config: dict[str, Any], manifest: dict[str, Any]) -> None:
    """The pinned Phase 2 configuration must be the configuration in use now."""
    segmentation = load_segmentation_config()
    quality = load_quality_config()
    provenance = manifest.get("provenance") or {}

    checks = (
        (
            "segmentation_config_version",
            config.get("segmentation_config_version"),
            segmentation.segmentation_config_version,
        ),
        (
            "segmentation_config_sha256",
            config.get("segmentation_config_sha256"),
            segmentation.content_sha256,
        ),
        (
            "quality_config_version",
            config.get("quality_config_version"),
            quality.quality_config_version,
        ),
        (
            "quality_config_sha256",
            config.get("quality_config_sha256"),
            quality.content_sha256,
        ),
    )
    for key, bundled, active in checks:
        if bundled != active:
            raise ConfigMismatchError(
                f"bundle {key} {bundled!r} does not match the active configuration "
                f"({active!r}); features are not comparable"
            )
        if provenance.get(key) != bundled:
            raise ConfigMismatchError(
                f"manifest provenance {key} {provenance.get(key)!r} disagrees with the "
                f"bundled {bundled!r}"
            )


def load_bundle(bundle_dir: Path | str | None = None) -> LoadedBundle:
    """Load and fully verify the production bundle. Never fits or retrains."""
    directory = Path(bundle_dir) if bundle_dir is not None else _default_bundle_dir()

    manifest = _read_json(directory / MANIFEST_FILE, error=BundleIntegrityError)
    schema = _read_json(directory / SCHEMA_FILE, error=BundleIntegrityError)
    config = _read_json(directory / CONFIG_FILE, error=BundleIntegrityError)
    _read_json(directory / PREPROCESSING_FILE, error=BundleIntegrityError)
    _read_json(directory / EVALUATION_FILE, error=BundleIntegrityError)

    verify_artifact_hashes(directory, manifest)
    verify_schema(schema, manifest)
    verify_config(config, manifest)

    model_path = directory / MODEL_FILE
    if not model_path.exists():
        raise BundleIntegrityError(f"missing artifact: {MODEL_FILE}")
    pipeline = joblib.load(model_path)

    steps = tuple(name for name, _ in getattr(pipeline, "steps", ()))
    if steps != EXPECTED_PIPELINE_STEPS:
        raise BundleIntegrityError(
            f"pipeline steps {steps} are not {EXPECTED_PIPELINE_STEPS}"
        )
    if int(getattr(pipeline, "n_features_in_", 0)) != EXPECTED_FEATURE_COUNT:
        raise SchemaMismatchError(
            f"pipeline expects {getattr(pipeline, 'n_features_in_', None)} features, "
            f"the schema declares {EXPECTED_FEATURE_COUNT}"
        )

    classes = tuple(str(label) for label in getattr(pipeline, "classes_", ()))
    declared = tuple(schema.get("classes") or ())
    if classes != declared:
        raise SchemaMismatchError(
            f"pipeline classes {list(classes)} do not match the packaged classes "
            f"{list(declared)}"
        )

    return LoadedBundle(
        bundle_dir=directory,
        pipeline=pipeline,
        manifest=manifest,
        schema=schema,
        config=config,
        classes=classes,
        feature_names=FEATURE_NAMES,
    )


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class InferenceService:
    """Holds one verified bundle and scores feature vectors against it."""

    def __init__(self, bundle: LoadedBundle) -> None:
        self._bundle = bundle

    @classmethod
    def from_bundle_dir(cls, bundle_dir: Path | str | None = None) -> "InferenceService":
        return cls(load_bundle(bundle_dir))

    @property
    def bundle(self) -> LoadedBundle:
        return self._bundle

    @property
    def model_version(self) -> str:
        return self._bundle.model_version

    @property
    def classes(self) -> tuple[str, ...]:
        return self._bundle.classes

    def _check_feature_provenance(self, result: FeatureExtractionResult) -> None:
        """Reject a vector produced by a different schema or configuration."""
        version = getattr(result, "schema_version", FEATURE_SET_VERSION)
        if version != self._bundle.feature_set_version:
            raise SchemaMismatchError(
                f"feature result schema {version!r} is not the bundle's "
                f"{self._bundle.feature_set_version!r}"
            )
        for label, value, expected in (
            (
                "segmentation_config_sha256",
                result.segmentation_config_sha256,
                self._bundle.segmentation_config_sha256,
            ),
            (
                "quality_config_sha256",
                result.quality_config_sha256,
                self._bundle.quality_config_sha256,
            ),
        ):
            if value and value != expected:
                raise ConfigMismatchError(
                    f"feature result {label} {value[:12]}... was produced by a "
                    f"different configuration ({expected[:12]}...); features are not "
                    "comparable"
                )

    def predict(self, result: FeatureExtractionResult) -> PredictionOutcome:
        """Score one feature-extraction result. Never zero-fills, never retrains."""
        if result.values is None:
            raise UnusableFeatureVectorError(
                "the feature result carries no vector (rejected image); there is "
                "nothing honest to classify"
            )
        self._check_feature_provenance(result)

        vector = np.asarray(result.values, dtype=np.float64).reshape(1, -1)
        if vector.shape[1] != EXPECTED_FEATURE_COUNT:  # pragma: no cover - schema guard
            raise SchemaMismatchError(
                f"feature vector has {vector.shape[1]} values, expected "
                f"{EXPECTED_FEATURE_COUNT}"
            )

        label = str(self._bundle.pipeline.predict(vector)[0])
        if label not in self._bundle.classes:  # pragma: no cover - estimator invariant
            raise InferenceError(f"pipeline returned an unknown label {label!r}")

        raw_scores = np.asarray(
            self._bundle.pipeline.decision_function(vector), dtype=np.float64
        ).reshape(-1)
        if raw_scores.shape[0] != len(self._bundle.classes):
            raise InferenceError(
                f"decision_function returned {raw_scores.shape[0]} scores for "
                f"{len(self._bundle.classes)} classes"
            )

        decision_scores = {
            name: float(score) for name, score in zip(self._bundle.classes, raw_scores)
        }
        ordered = sorted(decision_scores.items(), key=lambda item: item[1], reverse=True)
        margin = float(ordered[0][1] - ordered[1][1]) if len(ordered) > 1 else 0.0

        return PredictionOutcome(
            label=label,
            decision_scores=decision_scores,
            margin=margin,
            ranking=tuple(name for name, _ in ordered),
            model_name=self._bundle.model_name,
            model_version=self._bundle.model_version,
            feature_set_version=self._bundle.feature_set_version,
            segmentation_config_version=self._bundle.segmentation_config_version,
            quality_config_version=self._bundle.quality_config_version,
            status=str(result.status),
            lesion_reliable=bool(result.lesion_reliable),
            lesion_area_percentage=result.lesion_area_percentage,
            warnings=tuple(result.warnings),
            missing_features=tuple(result.missing_features),
        )


# --------------------------------------------------------------------------- #
# Startup hook: load once per process
# --------------------------------------------------------------------------- #

_service: InferenceService | None = None
_service_lock = threading.Lock()


def get_inference_service() -> InferenceService:
    """Return the process-wide service, loading the bundle on first use only."""
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = InferenceService.from_bundle_dir()
    return _service


def reset_inference_service() -> None:
    """Drop the cached service (tests and explicit reloads only)."""
    global _service
    with _service_lock:
        _service = None
