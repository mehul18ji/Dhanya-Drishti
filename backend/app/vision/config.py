"""Validated, versioned loaders for the YAML pipeline configuration.

PRD §9 requires every segmentation threshold, kernel size and K-Means setting to
live in configuration files rather than in unrelated modules. This module is the
single entry point: it parses the YAML, rejects typos and impossible values, and
records the exact file hash so reports can state which configuration produced
them.

Nothing here imports OpenCV, so configuration can be validated cheaply.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# backend/app/vision/config.py -> parents[2] == backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BACKEND_DIR / "configs"
DEFAULT_SEGMENTATION_PATH = CONFIG_DIR / "segmentation.yaml"
DEFAULT_QUALITY_PATH = CONFIG_DIR / "quality_thresholds.yaml"


class _StrictModel(BaseModel):
    """Base model: reject unknown keys so a typo cannot silently disable logic."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class HsvRange(_StrictModel):
    h_min: int = Field(ge=0, le=179)
    h_max: int = Field(ge=0, le=179)
    s_min: int = Field(ge=0, le=255)
    v_min: int = Field(ge=0, le=255)

    @model_validator(mode="after")
    def _ordered(self) -> "HsvRange":
        if self.h_min > self.h_max:
            raise ValueError(f"h_min ({self.h_min}) must be <= h_max ({self.h_max})")
        return self


class LeafHsvSettings(_StrictModel):
    green: HsvRange
    yellow: HsvRange
    brown: HsvRange


class LabRange(_StrictModel):
    enabled: bool = True
    l_min: int = Field(ge=0, le=255)
    l_max: int = Field(ge=0, le=255)
    a_min: int = Field(ge=0, le=255)
    a_max: int = Field(ge=0, le=255)
    b_min: int = Field(ge=0, le=255)
    b_max: int = Field(ge=0, le=255)
    min_chroma: int = Field(ge=0, le=255, default=10)

    @model_validator(mode="after")
    def _ordered(self) -> "LabRange":
        for minimum, maximum, name in (
            (self.l_min, self.l_max, "l"),
            (self.a_min, self.a_max, "a"),
            (self.b_min, self.b_max, "b"),
        ):
            if minimum > maximum:
                raise ValueError(f"{name}_min ({minimum}) must be <= {name}_max ({maximum})")
        return self


class _KMeansBase(_StrictModel):
    enabled: bool = True
    k: int = Field(ge=2, le=8)
    sample_pixels: int = Field(ge=100, le=2_000_000)
    random_state: int = Field(ge=0)
    n_init: int = Field(ge=1, le=100)
    max_iter: int = Field(ge=10, le=10_000)


class KMeansSettings(_KMeansBase):
    # A cluster is tissue only if its centroid is visibly coloured. Warm-toned
    # paper sits around S=20-25 and must never be accepted, no matter how much
    # of the colour mask leaks into its cluster.
    min_cluster_saturation: int = Field(ge=0, le=255)


class LesionKMeansSettings(_KMeansBase):
    hue_delta_min: float = Field(ge=0.0, le=179.0)
    lab_a_delta_min: float = Field(ge=0.0, le=255.0)
    value_drop_ratio: float = Field(gt=0.0, le=1.0)


class _MorphologyBase(_StrictModel):
    open_kernel: int = Field(ge=1, le=99)
    close_kernel: int = Field(ge=1, le=99)
    open_iterations: int = Field(ge=0, le=20)
    close_iterations: int = Field(ge=0, le=20)

    @model_validator(mode="after")
    def _odd_kernels(self) -> "_MorphologyBase":
        for name in ("open_kernel", "close_kernel"):
            value = getattr(self, name)
            if value % 2 == 0:
                raise ValueError(f"{name} must be odd, got {value}")
        return self


class MorphologySettings(_MorphologyBase):
    min_component_area_fraction: float = Field(ge=0.0, le=1.0)


class LesionMorphologySettings(_MorphologyBase):
    """Same kernels as leaf morphology, without the component-area key."""




class CandidateSettings(_StrictModel):
    min_area_fraction: float = Field(ge=0.0, le=1.0)
    min_fill_ratio: float = Field(ge=0.0, le=1.0)
    centrality_weight: float = Field(ge=0.0, le=10.0)
    border_penalty: float = Field(ge=0.0, le=1.0)
    border_touch_band_px: int = Field(ge=0, le=100)


class FallbackSettings(_StrictModel):
    enabled: bool = True
    leaf_green_fraction_threshold: float = Field(gt=0.0, le=1.0)
    candidate_area_fraction_for_full_frame: float = Field(gt=0.0, le=1.0)


class MultiLeafSettings(_StrictModel):
    enabled: bool = True
    secondary_area_ratio: float = Field(gt=0.0, le=1.0)
    secondary_centrality_min: float = Field(ge=0.0, le=1.0)
    secondary_centroid_distance_ratio: float = Field(ge=0.0, le=1.0)


class DenoiseSettings(_StrictModel):
    method: Literal["none", "bilateral", "fast_nlmeans"] = "bilateral"
    bilateral_diameter: int = Field(ge=1, le=31)
    bilateral_sigma_color: float = Field(ge=0.0)
    bilateral_sigma_space: float = Field(ge=0.0)
    nlmeans_h: float = Field(ge=0.0)
    nlmeans_template_window: int = Field(ge=1, le=31)
    nlmeans_search_window: int = Field(ge=1, le=61)


class PreprocessingSettings(_StrictModel):
    working_long_side: int = Field(ge=64, le=4096)
    canvas_size: int = Field(ge=64, le=2048)
    pad_value: int = Field(ge=0, le=255)
    crop_margin_fraction: float = Field(ge=0.0, le=0.5)
    denoise: DenoiseSettings

    @model_validator(mode="after")
    def _canvas_fits(self) -> "PreprocessingSettings":
        if self.canvas_size > self.working_long_side:
            raise ValueError(
                "canvas_size must not exceed working_long_side; upsampling a crop "
                "cannot add detail"
            )
        return self


class LeafSettings(_StrictModel):
    hsv: LeafHsvSettings
    lab: LabRange
    kmeans: KMeansSettings
    morphology: MorphologySettings
    candidate: CandidateSettings
    fallback: FallbackSettings
    multi_leaf: MultiLeafSettings
    border_erosion_px: int = Field(ge=0, le=100)


class LesionSettings(_StrictModel):
    border_exclusion_px: int = Field(ge=0, le=100)
    min_saturation: int = Field(ge=0, le=255)
    min_value: int = Field(ge=0, le=255)
    hue_delta_min: float = Field(ge=0.0, le=179.0)
    lab_a_delta_min: float = Field(ge=0.0, le=255.0)
    lab_b_delta_min: float = Field(ge=0.0, le=255.0)
    value_drop_ratio: float = Field(gt=0.0, le=1.0)
    green_hue_tolerance: float = Field(ge=0.0, le=179.0)
    green_lab_a_tolerance: float = Field(ge=0.0, le=255.0)
    green_lab_b_tolerance: float = Field(ge=0.0, le=255.0)
    kmeans: LesionKMeansSettings
    morphology: LesionMorphologySettings
    min_lesion_area_fraction_of_leaf: float = Field(ge=0.0, le=1.0)
    max_plausible_lesion_fraction: float = Field(gt=0.0, le=1.0)
    # Relative lesion colour needs enough healthy-green tissue to reference.
    min_healthy_reference_fraction: float = Field(gt=0.0, le=1.0)


class SegmentationConfig(_StrictModel):
    segmentation_config_version: str = Field(min_length=1, max_length=64)
    preprocessing: PreprocessingSettings
    leaf: LeafSettings
    lesion: LesionSettings
    # Filled in by the loader; never read from YAML.
    source_path: str = ""
    content_sha256: str = ""


class DimensionLimits(_StrictModel):
    hard_reject_short_side_px: int = Field(ge=1)
    soft_warn_short_side_px: int = Field(ge=1)
    hard_reject_total_pixels: int = Field(ge=1)
    soft_warn_total_pixels: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "DimensionLimits":
        if self.hard_reject_short_side_px > self.soft_warn_short_side_px:
            raise ValueError("hard reject short side must be <= soft warn short side")
        if self.hard_reject_total_pixels > self.soft_warn_total_pixels:
            raise ValueError("hard reject total pixels must be <= soft warn total pixels")
        return self


class BrightnessLimits(_StrictModel):
    hard_reject_mean_v_below: float = Field(ge=0.0, le=255.0)
    hard_reject_mean_v_above: float = Field(ge=0.0, le=255.0)
    warn_mean_v_below: float = Field(ge=0.0, le=255.0)
    warn_mean_v_above: float = Field(ge=0.0, le=255.0)

    @model_validator(mode="after")
    def _ordered(self) -> "BrightnessLimits":
        if self.hard_reject_mean_v_below > self.warn_mean_v_below:
            raise ValueError("hard reject low brightness must be <= warn low brightness")
        if self.hard_reject_mean_v_above < self.warn_mean_v_above:
            raise ValueError("hard reject high brightness must be >= warn high brightness")
        return self


class ContrastLimits(_StrictModel):
    hard_reject_std_v_below: float = Field(ge=0.0)
    warn_std_v_below: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _ordered(self) -> "ContrastLimits":
        if self.hard_reject_std_v_below > self.warn_std_v_below:
            raise ValueError("hard reject contrast must be <= warn contrast")
        return self


class ExposureLimits(_StrictModel):
    leaf_overexposed_v_above: int = Field(ge=0, le=255)
    hard_reject_leaf_overexposed_fraction_above: float = Field(ge=0.0, le=1.0)
    warn_leaf_overexposed_fraction_above: float = Field(ge=0.0, le=1.0)
    underexposed_v_below: int = Field(ge=0, le=255)
    warn_leaf_underexposed_fraction_above: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> "ExposureLimits":
        if self.warn_leaf_overexposed_fraction_above > self.hard_reject_leaf_overexposed_fraction_above:
            raise ValueError("warn over-exposure fraction must be <= hard reject fraction")
        return self


class BlurLimits(_StrictModel):
    hard_reject_laplacian_variance_below: float = Field(ge=0.0)
    warn_laplacian_variance_below: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _ordered(self) -> "BlurLimits":
        if self.hard_reject_laplacian_variance_below > self.warn_laplacian_variance_below:
            raise ValueError("hard reject blur must be <= warn blur")
        return self


class LeafQualityLimits(_StrictModel):
    hard_reject_area_fraction_below: float = Field(ge=0.0, le=1.0)
    warn_area_fraction_below: float = Field(ge=0.0, le=1.0)
    warn_full_frame_fallback: bool = True
    warn_multi_leaf: bool = True
    warn_weak_fill_ratio_below: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> "LeafQualityLimits":
        if self.hard_reject_area_fraction_below > self.warn_area_fraction_below:
            raise ValueError("hard reject leaf area must be <= warn leaf area")
        return self


class SegmentationQualityLimits(_StrictModel):
    warn_lesion_fraction_above: float = Field(ge=0.0, le=1.0)


class QualityConfig(_StrictModel):
    quality_config_version: str = Field(min_length=1, max_length=64)
    dimensions: DimensionLimits
    brightness: BrightnessLimits
    contrast: ContrastLimits
    exposure: ExposureLimits
    blur: BlurLimits
    leaf: LeafQualityLimits
    segmentation: SegmentationQualityLimits
    source_path: str = ""
    content_sha256: str = ""


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


@lru_cache(maxsize=8)
def _load_segmentation_cached(path_string: str) -> tuple[SegmentationConfig, str]:
    path = Path(path_string)
    raw = path.read_bytes()
    config = SegmentationConfig.model_validate(_read_yaml(path))
    return config, hashlib.sha256(raw).hexdigest()


def load_segmentation_config(path: str | Path | None = None) -> SegmentationConfig:
    """Load and validate `segmentation.yaml`, recording its exact hash."""
    resolved = (Path(path) if path is not None else DEFAULT_SEGMENTATION_PATH).resolve()
    config, digest = _load_segmentation_cached(str(resolved))
    return config.model_copy(update={"source_path": str(resolved), "content_sha256": digest})


@lru_cache(maxsize=8)
def _load_quality_cached(path_string: str) -> tuple[QualityConfig, str]:
    path = Path(path_string)
    raw = path.read_bytes()
    config = QualityConfig.model_validate(_read_yaml(path))
    return config, hashlib.sha256(raw).hexdigest()


def load_quality_config(path: str | Path | None = None) -> QualityConfig:
    """Load and validate `quality_thresholds.yaml`, recording its exact hash."""
    resolved = (Path(path) if path is not None else DEFAULT_QUALITY_PATH).resolve()
    config, digest = _load_quality_cached(str(resolved))
    return config.model_copy(update={"source_path": str(resolved), "content_sha256": digest})
