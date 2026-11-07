"""Relative-colour lesion segmentation on the letterboxed canvas (PRD §9C).

Lesions are defined **relative to the leaf**, never by absolute colour alone:

- a hue shift away from the healthy-green leaf median,
- a rise in the Lab a* channel (redder/browner tissue),
- a fall in Lab b* or HSV V (darker/yellower tissue),
- a seeded K-Means cluster whose centroid shows the same shifts.

White paper, grey shadow and black text are neutral and are excluded by the
saturation/value guards. Everything is intersected with the leaf mask so the
background can never become a lesion. Morphology removes speckle, and a narrow
border exclusion prevents the anti-aliased leaf edge from becoming a lesion
ring.
"""

from __future__ import annotations

import warnings as warnings_module

import cv2
import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning

from app.vision.config import SegmentationConfig
from app.vision.types import LesionSegmentationResult


def _remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    if min_area <= 1:
        return mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cleaned = mask.copy()
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < min_area:
            cleaned[labels == label] = 0
    return cleaned


def _leaf_statistics(
    hsv: np.ndarray,
    lab: np.ndarray,
    leaf_binary: np.ndarray,
    erosion_px: int,
    min_reference_fraction: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, float] | None]:
    """Median colour of healthy-looking tissue inside the eroded leaf mask.

    Returns ``(stats_mask, green_pixels, medians)``. ``medians`` is ``None`` when
    the leaf has too little healthy-green tissue left to serve as a reference.
    Using the necrotic tissue as its own reference would make every leaf look
    healthy (an almost fully brown leaf reported "0 % lesions"), so the caller
    must report an unreliable estimate instead.
    """
    if erosion_px > 0:
        kernel = np.ones((2 * erosion_px + 1, 2 * erosion_px + 1), dtype=np.uint8)
        stats_mask = cv2.erode(leaf_binary.astype(np.uint8), kernel) > 0
        if stats_mask.sum() < 100:
            stats_mask = leaf_binary
    else:
        stats_mask = leaf_binary

    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    green_pixels = (
        stats_mask
        & (hue >= 25)
        & (hue <= 100)
        & (saturation >= 35)
        & (value >= 20)
    )

    leaf_area = int(leaf_binary.sum())
    required = max(100, int(round(min_reference_fraction * leaf_area)))
    if int(green_pixels.sum()) < required:
        return stats_mask, green_pixels, None

    medians = {
        "hue": float(np.median(hue[green_pixels])),
        "saturation": float(np.median(saturation[green_pixels])),
        "value": float(np.median(value[green_pixels])),
        "l": float(np.median(lab[:, :, 0][green_pixels])),
        "a": float(np.median(lab[:, :, 1][green_pixels])),
        "b": float(np.median(lab[:, :, 2][green_pixels])),
    }
    return stats_mask, green_pixels, medians


def _hue_distance(hue: np.ndarray, reference: float) -> np.ndarray:
    delta = np.abs(hue.astype(np.float32) - reference)
    return np.minimum(delta, 179.0 - delta)


def _kmeans_lesion_mask(
    bgr: np.ndarray,
    leaf_binary: np.ndarray,
    medians: dict[str, float],
    config: SegmentationConfig,
) -> np.ndarray:
    settings = config.lesion.kmeans
    if not settings.enabled:
        return np.zeros(leaf_binary.shape, dtype=np.uint8)

    pixels = bgr[leaf_binary]
    total = pixels.shape[0]
    if total < max(10, settings.k * 10):
        return np.zeros(leaf_binary.shape, dtype=np.uint8)
    sample_size = min(settings.sample_pixels, total)
    rng = np.random.default_rng(settings.random_state)
    if sample_size < total:
        indices = rng.choice(total, size=sample_size, replace=False)
    else:
        indices = np.arange(total)

    model = KMeans(
        n_clusters=settings.k,
        random_state=settings.random_state,
        n_init=settings.n_init,
        max_iter=settings.max_iter,
    )
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("ignore", ConvergenceWarning)
        model.fit(pixels[indices].astype(np.float32))

    labels = model.predict(pixels.astype(np.float32))

    lesion = np.zeros(leaf_binary.shape, dtype=np.uint8)
    flat_indices = np.flatnonzero(leaf_binary.reshape(-1))

    for cluster_index in range(settings.k):
        cluster_pixels = pixels[labels == cluster_index]
        if cluster_pixels.shape[0] == 0:
            continue

        centroid = cluster_pixels.mean(axis=0).astype(np.float32).reshape(1, 1, 3)
        centroid_hsv = cv2.cvtColor(centroid.astype(np.uint8), cv2.COLOR_BGR2HSV)[0, 0]
        centroid_lab = cv2.cvtColor(centroid.astype(np.uint8), cv2.COLOR_BGR2LAB)[0, 0]

        hue_delta = float(
            _hue_distance(np.float32(centroid_hsv[0]), medians["hue"])
        )
        a_delta = float(centroid_lab[1]) - medians["a"]
        value_ratio = float(centroid_hsv[2]) / max(1.0, medians["value"])

        is_lesion = (
            hue_delta > settings.hue_delta_min
            or a_delta > settings.lab_a_delta_min
            or value_ratio < settings.value_drop_ratio
        )
        if is_lesion:
            cluster_mask = labels == cluster_index
            lesion.reshape(-1)[flat_indices[cluster_mask]] = 255

    return lesion


def _unreliable_no_reference(
    hsv: np.ndarray,
    leaf_mask: np.ndarray,
    leaf_binary: np.ndarray,
    leaf_area: int,
    config: SegmentationConfig,
) -> LesionSegmentationResult:
    """Honest fallback when no healthy-green reference exists.

    Every sufficiently coloured pixel inside the leaf is reported as potentially
    diseased and the result is marked unreliable, so the API can answer
    ``uncertain`` rather than inventing a confident lesion percentage.
    """
    settings = config.lesion
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    tissue = (
        leaf_binary
        & (saturation >= settings.min_saturation)
        & (value >= settings.min_value)
        & (value <= 254)
    )
    mask = cv2.bitwise_and(tissue.astype(np.uint8) * 255, leaf_mask)
    lesion_pixels = int((mask > 0).sum())
    fraction = lesion_pixels / leaf_area if leaf_area else 0.0

    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    component_areas = [
        int(stats[label, cv2.CC_STAT_AREA])
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] > 0
    ]
    lesion_count = len(component_areas)
    largest = max(component_areas) / leaf_area if component_areas else 0.0
    mean = (sum(component_areas) / lesion_count) / leaf_area if component_areas else 0.0

    return LesionSegmentationResult(
        mask=mask,
        lesion_area_fraction=fraction,
        lesion_count=lesion_count,
        largest_lesion_fraction=largest,
        mean_lesion_area_fraction=mean,
        method="no_healthy_reference",
        warnings=("WEAK_LESION_MASK", "LESION_REFERENCE_UNAVAILABLE"),
        reliable=False,
    )


def segment_lesions(
    canvas_bgr: np.ndarray,
    leaf_mask: np.ndarray,
    config: SegmentationConfig,
) -> LesionSegmentationResult:
    """Segment lesions inside the leaf; deterministic for a given canvas."""
    settings = config.lesion
    leaf_binary = leaf_mask > 0
    leaf_area = int(leaf_binary.sum())

    if leaf_area < 100:
        return LesionSegmentationResult(
            mask=np.zeros(leaf_binary.shape, dtype=np.uint8),
            lesion_area_fraction=0.0,
            lesion_count=0,
            largest_lesion_fraction=0.0,
            mean_lesion_area_fraction=0.0,
            method="relative_colour_kmeans",
            warnings=("WEAK_LESION_MASK",),
        )

    hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2LAB)
    _, _, medians = _leaf_statistics(
        hsv,
        lab,
        leaf_binary,
        config.leaf.border_erosion_px,
        settings.min_healthy_reference_fraction,
    )
    if medians is None:
        return _unreliable_no_reference(hsv, leaf_mask, leaf_binary, leaf_area, config)

    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    a_channel = lab[:, :, 1]
    b_channel = lab[:, :, 2]

    hue_delta = _hue_distance(hue, medians["hue"])
    shifted = (
        (hue_delta > settings.hue_delta_min)
        | (a_channel.astype(np.float32) > medians["a"] + settings.lab_a_delta_min)
        | (b_channel.astype(np.float32) < medians["b"] - settings.lab_b_delta_min)
        | (value.astype(np.float32) < medians["value"] * settings.value_drop_ratio)
    )
    healthy_green = (
        (hue_delta <= settings.green_hue_tolerance)
        & (
            np.abs(a_channel.astype(np.float32) - medians["a"])
            <= settings.green_lab_a_tolerance
        )
        & (
            np.abs(b_channel.astype(np.float32) - medians["b"])
            <= settings.green_lab_b_tolerance
        )
        & (value.astype(np.float32) >= medians["value"] * 0.75)
    )
    valid_tissue = (
        (saturation >= settings.min_saturation)
        & (value >= settings.min_value)
        & (value <= 254)
    )

    relative = shifted & ~healthy_green & valid_tissue & leaf_binary

    kmeans_mask = _kmeans_lesion_mask(canvas_bgr, leaf_binary, medians, config)
    lesion = np.logical_or(relative, kmeans_mask > 0).astype(np.uint8) * 255
    lesion = cv2.bitwise_and(lesion, leaf_mask)

    morphology = settings.morphology
    if morphology.open_iterations:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (morphology.open_kernel, morphology.open_kernel)
        )
        lesion = cv2.morphologyEx(
            lesion, cv2.MORPH_OPEN, kernel, iterations=morphology.open_iterations
        )
    if morphology.close_iterations:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (morphology.close_kernel, morphology.close_kernel)
        )
        lesion = cv2.morphologyEx(
            lesion, cv2.MORPH_CLOSE, kernel, iterations=morphology.close_iterations
        )

    min_area = max(1, int(round(settings.min_lesion_area_fraction_of_leaf * leaf_area)))
    lesion = _remove_small(lesion, min_area)

    if settings.border_exclusion_px > 0:
        kernel = np.ones(
            (2 * settings.border_exclusion_px + 1, 2 * settings.border_exclusion_px + 1),
            dtype=np.uint8,
        )
        inner_leaf = cv2.erode(leaf_mask, kernel)
        if int((inner_leaf > 0).sum()) > int(0.5 * leaf_area):
            lesion = cv2.bitwise_and(lesion, inner_leaf)

    lesion_binary = lesion > 0
    lesion_pixels = int(lesion_binary.sum())
    fraction = lesion_pixels / leaf_area if leaf_area else 0.0

    count, _, stats, _ = cv2.connectedComponentsWithStats(lesion, connectivity=8)
    component_areas = [
        int(stats[label, cv2.CC_STAT_AREA])
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] > 0
    ]
    lesion_count = len(component_areas)
    largest = max(component_areas) / leaf_area if component_areas else 0.0
    mean = (sum(component_areas) / lesion_count) / leaf_area if component_areas else 0.0

    warnings: tuple[str, ...] = ()
    if fraction > settings.max_plausible_lesion_fraction:
        warnings = ("WEAK_LESION_MASK",)

    return LesionSegmentationResult(
        mask=lesion,
        lesion_area_fraction=fraction,
        lesion_count=lesion_count,
        largest_lesion_fraction=largest,
        mean_lesion_area_fraction=mean,
        method="relative_colour_kmeans",
        warnings=warnings,
        reliable=True,
    )
