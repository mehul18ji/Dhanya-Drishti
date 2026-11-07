"""Versioned numerical feature extraction (PRD §9 Stage D).

This is the **single source of truth** for the classifier's feature vector:
Phase 3 training and Phase 4 inference both call
:func:`extract_features_from_pipeline` and receive a vector in exactly the order
declared by :data:`FEATURE_NAMES`. Changing that order requires bumping
:data:`FEATURE_SET_VERSION`; a saved model is only valid for the schema version
recorded in its manifest.

Feature groups (all computed on the letterboxed 512 px processing canvas, so no
raw resolution ever enters the vector — decision/risk R3):

- **colour**   — per-channel mean/std for RGB, HSV and Lab plus four
  robust histogram quantiles, all normalised to ``0..1``.
- **texture**  — GLCM over the leaf's own greyscale, averaged over four angles.
- **shape**    — scale-invariant leaf geometry (area, perimeter, solidity, ...).
- **lesion**   — lesion extent and lesion geometry relative to the leaf.
- **spatial**  — where the lesions sit inside the leaf.

Honesty rule for lesions (Phase 3 input contract): when the lesion stage could
not be calibrated (``LesionSegmentationResult.reliable is False``, e.g.
``LESION_REFERENCE_UNAVAILABLE`` on a fully necrotic leaf) the lesion and spatial
features are **not** written as ``0.0``. They are written as ``NaN`` and listed in
``missing_features``, and ``lesion_area_percentage`` is ``None``. A measured zero
and an unmeasurable value are different facts and must never be confused.

Locked Phase 3 rule (decision P-13): raw feature matrices preserve ``NaN`` for
unreliable lesion/spatial features. Any later classifier training must fit
missing-value imputation and missingness indicators **inside** the scikit-learn
pipeline, on each training fold only. Uncertain lesion values are never replaced
with ``0.0`` and images are never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from pathlib import Path
from typing import Any, Final, Literal

import cv2
import numpy as np
from skimage.feature import graycoprops, graycomatrix

from app.vision.config import (
    QualityConfig,
    SegmentationConfig,
    load_quality_config,
    load_segmentation_config,
)
from app.vision.pipeline import SegmentationPipelineResult, run_segmentation
from app.vision.types import LesionSegmentationResult

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

FEATURE_SET_VERSION: Final[str] = "1.0.0"
SCHEMA_NAME: Final[str] = "dhanyadrishti-leaf-features"

# GLCM settings are part of the schema version: changing them changes the vector.
GLCM_LEVELS: Final[int] = 32
GLCM_DISTANCES: Final[tuple[int, ...]] = (1,)
GLCM_ANGLES: Final[tuple[float, ...]] = (0.0, pi / 4, pi / 2, 3 * pi / 4)
GLCM_PROPERTIES: Final[tuple[str, ...]] = (
    "contrast",
    "dissimilarity",
    "homogeneity",
    "energy",
    "correlation",
)

COLOUR_FEATURES: Final[tuple[str, ...]] = (
    "rgb_r_mean",
    "rgb_r_std",
    "rgb_g_mean",
    "rgb_g_std",
    "rgb_b_mean",
    "rgb_b_std",
    "hsv_h_mean",
    "hsv_h_std",
    "hsv_s_mean",
    "hsv_s_std",
    "hsv_v_mean",
    "hsv_v_std",
    "lab_l_mean",
    "lab_l_std",
    "lab_a_mean",
    "lab_a_std",
    "lab_b_mean",
    "lab_b_std",
    "hsv_s_p90",
    "hsv_v_p10",
    "lab_a_p90",
    "lab_b_p90",
)

TEXTURE_FEATURES: Final[tuple[str, ...]] = (
    "glcm_contrast",
    "glcm_dissimilarity",
    "glcm_homogeneity",
    "glcm_energy",
    "glcm_correlation",
)

SHAPE_FEATURES: Final[tuple[str, ...]] = (
    "leaf_area_fraction",
    "leaf_fill_ratio",
    "leaf_aspect_ratio",
    "leaf_perimeter_ratio",
    "leaf_circularity",
    "leaf_solidity",
    "leaf_convexity",
    "leaf_equivalent_diameter_ratio",
)

LESION_FEATURES: Final[tuple[str, ...]] = (
    "lesion_area_ratio",
    "lesion_count_per_kpx",
    "lesion_largest_ratio",
    "lesion_mean_ratio",
    "lesion_perimeter_ratio",
    "lesion_compactness",
)

SPATIAL_FEATURES: Final[tuple[str, ...]] = (
    "lesion_centroid_dx",
    "lesion_centroid_dy",
    "lesion_spread_x",
    "lesion_spread_y",
    "lesion_border_mean_distance",
    "lesion_quadrant_tl_ratio",
    "lesion_quadrant_tr_ratio",
    "lesion_quadrant_bl_ratio",
    "lesion_quadrant_br_ratio",
)

FEATURE_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "colour": COLOUR_FEATURES,
    "texture": TEXTURE_FEATURES,
    "shape": SHAPE_FEATURES,
    "lesion": LESION_FEATURES,
    "spatial": SPATIAL_FEATURES,
}

FEATURE_NAMES: Final[tuple[str, ...]] = (
    COLOUR_FEATURES + TEXTURE_FEATURES + SHAPE_FEATURES + LESION_FEATURES + SPATIAL_FEATURES
)

#: Features that only exist when the lesion estimate is calibrated.
LESION_DEPENDENT_FEATURES: Final[tuple[str, ...]] = LESION_FEATURES + SPATIAL_FEATURES

_STATUS_CLEAN: Final[str] = "clean"
_STATUS_UNCERTAIN: Final[str] = "uncertain"
_STATUS_REJECTED: Final[str] = "rejected"

ExtractionStatus = Literal["clean", "uncertain", "rejected"]


def feature_schema() -> dict[str, Any]:
    """Return the machine-readable feature schema (no provenance filled in)."""
    return {
        "schema_name": SCHEMA_NAME,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_count": len(FEATURE_NAMES),
        "feature_names": list(FEATURE_NAMES),
        "groups": {name: list(names) for name, names in FEATURE_GROUPS.items()},
        "lesion_dependent_features": list(LESION_DEPENDENT_FEATURES),
        "missing_value_policy": (
            "Leak-free NaN sentinel: a lesion-dependent feature is NaN when the "
            "lesion estimate is not calibrated. It is never 0.0 in that case."
        ),
        "value_range": "all features are scale-invariant ratios or 0..1 normalised colours",
        "glcm": {
            "levels": GLCM_LEVELS,
            "distances": list(GLCM_DISTANCES),
            "angles_radians": [round(angle, 6) for angle in GLCM_ANGLES],
            "properties": list(GLCM_PROPERTIES),
            "region": "leaf bounding box, non-leaf pixels replaced by the leaf median grey",
        },
    }


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FeatureExtractionResult:
    """A feature vector plus everything needed to interpret it honestly.

    ``values`` is ``None`` for a rejected image: there is no honest feature
    vector to build, so nothing is substituted.
    """

    values: np.ndarray | None
    status: ExtractionStatus
    lesion_reliable: bool
    lesion_reference_available: bool
    lesion_area_percentage: float | None
    warnings: tuple[str, ...] = ()
    rejections: tuple[str, ...] = ()
    missing_features: tuple[str, ...] = ()
    schema_version: str = FEATURE_SET_VERSION
    segmentation_config_version: str = ""
    segmentation_config_sha256: str = ""
    quality_config_version: str = ""
    quality_config_sha256: str = ""
    stage_ms: dict[str, float] | None = None

    @property
    def usable(self) -> bool:
        """A vector exists and is not a rejected image."""
        return self.values is not None

    @property
    def feature_names(self) -> tuple[str, ...]:
        return FEATURE_NAMES

    def as_dict(self) -> dict[str, float | None]:
        """Feature name -> value, with ``None`` for unmeasurable features."""
        if self.values is None:
            return {name: None for name in FEATURE_NAMES}
        return {
            name: (None if np.isnan(value) else float(value))
            for name, value in zip(FEATURE_NAMES, self.values)
        }

    def schema(self) -> dict[str, Any]:
        """Schema plus the exact configuration provenance of this vector."""
        payload = feature_schema()
        payload.update(
            {
                "segmentation_config_version": self.segmentation_config_version,
                "segmentation_config_sha256": self.segmentation_config_sha256,
                "quality_config_version": self.quality_config_version,
                "quality_config_sha256": self.quality_config_sha256,
            }
        )
        return payload


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _to_float32(values: list[float], names: tuple[str, ...]) -> np.ndarray:
    """Build a float32 array in schema order, tolerating unmeasurable entries."""
    if len(values) != len(names):  # pragma: no cover - internal invariant
        raise ValueError(f"expected {len(names)} values, got {len(values)}")
    return np.asarray(values, dtype=np.float32)


def _safe(value: float) -> float:
    """Replace NaN/inf from degenerate geometry with 0.0 (measurable zero)."""
    return 0.0 if not np.isfinite(value) else float(value)


def _largest_contour(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(
        (mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _leaf_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    points = cv2.findNonZero((mask > 0).astype(np.uint8))
    if points is None:
        return None
    return tuple(int(v) for v in cv2.boundingRect(points))  # type: ignore[return-value]


def _colour_features(canvas_bgr: np.ndarray, leaf_mask: np.ndarray) -> list[float]:
    """Per-channel statistics of the leaf tissue only, normalised to 0..1."""
    binary = leaf_mask > 0
    bgr = canvas_bgr[binary].astype(np.float32)  # (N, 3) B,G,R
    hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)[binary].astype(np.float32)
    lab = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2LAB)[binary].astype(np.float32)

    # BGR -> RGB channel order for the reported names.
    rgb = bgr[:, ::-1]
    hue, saturation, value = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    lightness, a_channel, b_channel = lab[:, 0], lab[:, 1], lab[:, 2]

    channels = [
        (rgb[:, 0] / 255.0, 0.0),
        (rgb[:, 1] / 255.0, 0.0),
        (rgb[:, 2] / 255.0, 0.0),
        (hue / 179.0, 0.0),
        (saturation / 255.0, 0.0),
        (value / 255.0, 0.0),
        (lightness / 255.0, 0.0),
        (a_channel / 255.0, 0.0),
        (b_channel / 255.0, 0.0),
    ]

    values: list[float] = []
    for channel, _ in channels:
        values.append(_safe(float(channel.mean())))
        values.append(_safe(float(channel.std())))

    values.extend(
        [
            _safe(float(np.percentile(saturation, 90) / 255.0)),
            _safe(float(np.percentile(value, 10) / 255.0)),
            _safe(float(np.percentile(a_channel, 90) / 255.0)),
            _safe(float(np.percentile(b_channel, 90) / 255.0)),
        ]
    )
    return values


def _texture_features(
    canvas_bgr: np.ndarray, leaf_mask: np.ndarray
) -> list[float] | None:
    """GLCM statistics of the leaf's own greyscale texture.

    The GLCM is computed inside the leaf bounding box with non-leaf pixels set to
    the leaf's median grey, so background edges cannot masquerade as texture.
    """
    bbox = _leaf_bbox(leaf_mask)
    if bbox is None:
        return None
    x, y, width, height = bbox
    if width < 5 or height < 5:
        return None

    grey = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    crop = grey[y : y + height, x : x + width]
    crop_mask = leaf_mask[y : y + height, x : x + width] > 0
    if int(crop_mask.sum()) < 64:
        return None

    median = float(np.median(crop[crop_mask]))
    filled = np.where(crop_mask, crop, median)
    quantised = np.clip(
        (filled * (GLCM_LEVELS / 256.0)).astype(np.int32), 0, GLCM_LEVELS - 1
    ).astype(np.uint8)

    matrix = graycomatrix(
        quantised,
        distances=list(GLCM_DISTANCES),
        angles=list(GLCM_ANGLES),
        levels=GLCM_LEVELS,
        symmetric=True,
        normed=True,
    )
    values: list[float] = []
    for prop in GLCM_PROPERTIES:
        per_angle = graycoprops(matrix, prop)
        values.append(_safe(float(np.nanmean(per_angle))))
    return values


def _shape_features(leaf_mask: np.ndarray, canvas_size: int) -> list[float]:
    """Scale-invariant leaf geometry (never raw pixels or raw resolution)."""
    binary = (leaf_mask > 0).astype(np.uint8)
    canvas_area = float(canvas_size * canvas_size)
    area = float(int(binary.sum()))
    contour = _largest_contour(binary)
    bbox = _leaf_bbox(binary)

    perimeter = float(cv2.arcLength(contour, True)) if contour is not None else 0.0
    hull_area = 0.0
    hull_perimeter = 0.0
    if contour is not None and len(contour) >= 3:
        hull = cv2.convexHull(contour)
        hull_area = float(cv2.contourArea(hull))
        hull_perimeter = float(cv2.arcLength(hull, True))

    if bbox is None:
        return [0.0] * len(SHAPE_FEATURES)
    _, _, bbox_w, bbox_h = bbox
    short_side = float(min(bbox_w, bbox_h))
    long_side = float(max(bbox_w, bbox_h))

    circularity = (4.0 * pi * area / (perimeter**2)) if perimeter > 0 else 0.0
    equivalent_diameter = float(np.sqrt(4.0 * area / pi)) if area > 0 else 0.0

    return [
        _safe(area / canvas_area),
        _safe(area / float(bbox_w * bbox_h)) if bbox_w and bbox_h else 0.0,
        _safe(short_side / long_side) if long_side > 0 else 0.0,
        _safe(perimeter / float(canvas_size)),
        _safe(min(circularity, 1.0)),
        _safe(area / hull_area) if hull_area > 0 else 0.0,
        _safe(hull_perimeter / perimeter) if perimeter > 0 else 0.0,
        _safe(equivalent_diameter / float(canvas_size)),
    ]


def _lesion_features(lesion_mask: np.ndarray, leaf_mask: np.ndarray) -> list[float]:
    """Lesion extent and geometry relative to the leaf (never to the frame)."""
    lesion_binary = (lesion_mask > 0).astype(np.uint8)
    leaf_binary = (leaf_mask > 0).astype(np.uint8)
    leaf_area = float(int(leaf_binary.sum()))
    lesion_pixels = float(int(lesion_binary.sum()))

    count, _, stats, _ = cv2.connectedComponentsWithStats(lesion_binary, connectivity=8)
    component_areas = [
        float(stats[label, cv2.CC_STAT_AREA])
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] > 0
    ]
    largest = max(component_areas) if component_areas else 0.0
    mean_component = (sum(component_areas) / len(component_areas)) if component_areas else 0.0

    lesion_contour = _largest_contour(lesion_binary)
    lesion_perimeter = (
        float(cv2.arcLength(lesion_contour, True)) if lesion_contour is not None else 0.0
    )
    leaf_contour = _largest_contour(leaf_binary)
    leaf_perimeter = (
        float(cv2.arcLength(leaf_contour, True)) if leaf_contour is not None else 0.0
    )

    compactness = (
        4.0 * pi * lesion_pixels / (lesion_perimeter**2) if lesion_perimeter > 0 else 0.0
    )

    return [
        _safe(lesion_pixels / leaf_area) if leaf_area > 0 else 0.0,
        _safe(len(component_areas) / (leaf_area / 1000.0)) if leaf_area > 0 else 0.0,
        _safe(largest / leaf_area) if leaf_area > 0 else 0.0,
        _safe(mean_component / leaf_area) if leaf_area > 0 else 0.0,
        _safe(lesion_perimeter / leaf_perimeter) if leaf_perimeter > 0 else 0.0,
        _safe(min(compactness, 1.0)),
    ]


def _spatial_features(lesion_mask: np.ndarray, leaf_mask: np.ndarray) -> list[float]:
    """Where the lesions sit inside the leaf, in leaf-relative coordinates."""
    leaf_binary = (leaf_mask > 0).astype(np.uint8)
    lesion_binary = (lesion_mask > 0).astype(np.uint8)
    leaf_area = float(int(leaf_binary.sum()))
    lesion_pixels = float(int(lesion_binary.sum()))
    bbox = _leaf_bbox(leaf_binary)
    if bbox is None or lesion_pixels <= 0 or leaf_area <= 0:
        return [0.0] * len(SPATIAL_FEATURES)

    x, y, width, height = bbox
    leaf_y, leaf_x = np.nonzero(leaf_binary)
    lesion_y, lesion_x = np.nonzero(lesion_binary)

    leaf_cx, leaf_cy = float(leaf_x.mean()), float(leaf_y.mean())
    lesion_cx, lesion_cy = float(lesion_x.mean()), float(lesion_y.mean())

    spread_x = float(lesion_x.std()) / float(width) if width else 0.0
    spread_y = float(lesion_y.std()) / float(height) if height else 0.0

    # Mean distance from the lesion pixels to the nearest non-leaf pixel,
    # normalised by the leaf's equivalent radius.
    distance_to_edge = cv2.distanceTransform(leaf_binary, cv2.DIST_L2, 5)
    border_distance = float(distance_to_edge[lesion_binary > 0].mean())
    normaliser = float(np.sqrt(leaf_area / pi)) if leaf_area > 0 else 1.0

    mid_x = x + width / 2.0
    mid_y = y + height / 2.0
    left = lesion_x < mid_x
    top = lesion_y < mid_y
    quadrants = (
        float(np.count_nonzero(top & left)),
        float(np.count_nonzero(top & ~left)),
        float(np.count_nonzero(~top & left)),
        float(np.count_nonzero(~top & ~left)),
    )

    return [
        _safe((lesion_cx - leaf_cx) / float(width)) if width else 0.0,
        _safe((lesion_cy - leaf_cy) / float(height)) if height else 0.0,
        _safe(spread_x),
        _safe(spread_y),
        _safe(border_distance / normaliser) if normaliser > 0 else 0.0,
        *[_safe(count / lesion_pixels) for count in quadrants],
    ]


def _lesion_is_usable(lesion: LesionSegmentationResult | None) -> bool:
    """A lesion estimate is usable only when calibrated and free of reference faults."""
    if lesion is None:
        return False
    if not bool(getattr(lesion, "reliable", True)):
        return False
    return "LESION_REFERENCE_UNAVAILABLE" not in set(lesion.warnings)


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #


def extract_features_from_pipeline(
    result: SegmentationPipelineResult,
) -> FeatureExtractionResult:
    """Extract the versioned feature vector from one pipeline result.

    Training and inference both go through this function, so the vector a model
    was fitted on is the vector the API will produce (PRD §25 Phase 3 DoD).
    """
    warnings = tuple(issue.code for issue in result.quality.warnings)
    rejections = tuple(issue.code for issue in result.quality.rejections)

    canvas_bgr = result.canvas_bgr
    leaf_mask = result.canvas_leaf_mask
    lesion = result.lesion

    # No leaf means no honest feature vector. Nothing is zero-filled.
    if canvas_bgr is None or leaf_mask is None or not bool(result.leaf.found):
        return FeatureExtractionResult(
            values=None,
            status=_STATUS_REJECTED,
            lesion_reliable=False,
            lesion_reference_available=False,
            lesion_area_percentage=None,
            warnings=warnings,
            rejections=rejections or ("NO_CLEAR_LEAF_FOUND",),
            missing_features=FEATURE_NAMES,
            segmentation_config_version=result.segmentation_config_version,
            segmentation_config_sha256=result.segmentation_config_sha256,
            quality_config_version=result.quality_config_version,
            quality_config_sha256=result.quality_config_sha256,
            stage_ms=dict(result.stage_ms),
        )

    canvas_size = int(max(canvas_bgr.shape[0], canvas_bgr.shape[1]))
    lesion_usable = _lesion_is_usable(lesion)

    # Lesion-stage warnings are authoritative for the reference check; the
    # pipeline normally merges them into the quality report already, but this
    # extraction must not depend on that having happened.
    lesion_warnings = tuple(getattr(lesion, "warnings", ()) or ()) if lesion else ()
    all_warnings = warnings + tuple(code for code in lesion_warnings if code not in warnings)

    colour = _colour_features(canvas_bgr, leaf_mask)
    texture = _texture_features(canvas_bgr, leaf_mask)
    shape = _shape_features(leaf_mask, canvas_size)

    missing: list[str] = []
    lesion_values: list[float] = []
    spatial_values: list[float] = []

    if texture is None:
        # Too few leaf pixels for a meaningful GLCM: missing, not zero.
        missing.extend(TEXTURE_FEATURES)
    if lesion is None or not lesion_usable:
        missing.extend(LESION_DEPENDENT_FEATURES)
    else:
        lesion_values = _lesion_features(lesion.mask, leaf_mask)
        spatial_values = _spatial_features(lesion.mask, leaf_mask)

    nan = float("nan")
    values: list[float] = list(colour)
    values.extend([nan] * len(TEXTURE_FEATURES) if texture is None else texture)
    values.extend(shape)
    values.extend([nan] * len(LESION_FEATURES) if not lesion_values else lesion_values)
    values.extend([nan] * len(SPATIAL_FEATURES) if not spatial_values else spatial_values)

    vector = _to_float32(values, FEATURE_NAMES)

    if rejections:
        status: ExtractionStatus = _STATUS_REJECTED
    elif all_warnings or missing or not lesion_usable:
        status = _STATUS_UNCERTAIN
    else:
        status = _STATUS_CLEAN

    lesion_area_percentage: float | None = None
    if lesion is not None and lesion_usable:
        lesion_area_percentage = float(lesion.lesion_area_fraction) * 100.0

    return FeatureExtractionResult(
        values=vector,
        status=status,
        lesion_reliable=bool(lesion_usable),
        lesion_reference_available=(
            "LESION_REFERENCE_UNAVAILABLE" not in lesion_warnings
            and "LESION_REFERENCE_UNAVAILABLE" not in warnings
        ),
        lesion_area_percentage=lesion_area_percentage,
        warnings=all_warnings,
        rejections=rejections,
        missing_features=tuple(missing),
        segmentation_config_version=result.segmentation_config_version,
        segmentation_config_sha256=result.segmentation_config_sha256,
        quality_config_version=result.quality_config_version,
        quality_config_sha256=result.quality_config_sha256,
        stage_ms=dict(result.stage_ms),
    )


def extract_features(
    source: str | Path | bytes,
    *,
    segmentation_config: SegmentationConfig | None = None,
    quality_config: QualityConfig | None = None,
) -> FeatureExtractionResult:
    """Run the Phase 2 pipeline on one image and extract its feature vector."""
    result = run_segmentation(
        source,
        segmentation_config=segmentation_config or load_segmentation_config(),
        quality_config=quality_config or load_quality_config(),
    )
    return extract_features_from_pipeline(result)
