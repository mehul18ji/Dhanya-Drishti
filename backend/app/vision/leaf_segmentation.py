"""Deterministic classical leaf segmentation (PRD §9 Stage B).

Pipeline:

1. HSV candidate masks for green, yellowing and brown tissue.
2. An optional Lab chroma mask (neutral paper/grey/text is excluded).
3. Seeded K-Means colour clustering, merged with the colour evidence.
4. Morphological opening/closing and small-component removal.
5. Connected-component contours scored by area, convex-hull fill, centrality
   and border contact (never by "squareness" — leaves are long strips).
6. A documented full-frame fallback for background-free close-ups.
7. A multi-leaf warning when a second plausible leaf exists.

K-Means always uses the configured random seed, so the same image produces the
same mask on every run.
"""

from __future__ import annotations

import warnings as warnings_module
from dataclasses import dataclass

import cv2
import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning

from app.vision.config import HsvRange, LeafSettings, SegmentationConfig
from app.vision.types import LeafSegmentationResult


@dataclass(frozen=True)
class LeafCandidate:
    """Scored connected component before the primary leaf is chosen."""

    contour: np.ndarray
    area: float
    area_fraction: float
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    fill_ratio: float
    centrality: float
    border_touch: float
    score: float


def _range_mask(hsv: np.ndarray, limits: HsvRange) -> np.ndarray:
    lower = np.array([limits.h_min, limits.s_min, limits.v_min], dtype=np.uint8)
    upper = np.array([limits.h_max, 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lower, upper)


def build_colour_mask(bgr: np.ndarray, settings: LeafSettings) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(combined_leaf_mask, green_mask)``.

    The green mask drives the full-frame fallback (its 0.65 threshold was
    calibrated on the dataset); the combined mask also includes yellowing and
    brown tissue so lesions stay inside the leaf.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    green = _range_mask(hsv, settings.hsv.green)
    yellow = _range_mask(hsv, settings.hsv.yellow)
    brown = _range_mask(hsv, settings.hsv.brown)
    combined = cv2.bitwise_or(cv2.bitwise_or(green, yellow), brown)

    if settings.lab.enabled:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        light, a_channel, b_channel = cv2.split(lab)
        chroma = np.abs(a_channel.astype(np.int16) - 128) + np.abs(
            b_channel.astype(np.int16) - 128
        )
        lab_mask = (
            (light >= settings.lab.l_min)
            & (light <= settings.lab.l_max)
            & (a_channel >= settings.lab.a_min)
            & (a_channel <= settings.lab.a_max)
            & (b_channel >= settings.lab.b_min)
            & (b_channel <= settings.lab.b_max)
            & (chroma >= settings.lab.min_chroma)
        )
        combined = cv2.bitwise_or(combined, (lab_mask.astype(np.uint8) * 255))

    return combined, green


def build_kmeans_mask(
    bgr: np.ndarray,
    settings: LeafSettings,
) -> np.ndarray:
    """Cluster colours with a fixed seed and keep visibly coloured clusters."""
    kmeans = settings.kmeans
    if not kmeans.enabled:
        return np.zeros(bgr.shape[:2], dtype=np.uint8)

    height, width = bgr.shape[:2]
    pixels = bgr.reshape(-1, 3)
    total = pixels.shape[0]
    sample_size = min(kmeans.sample_pixels, total)

    rng = np.random.default_rng(kmeans.random_state)
    if sample_size < total:
        indices = rng.choice(total, size=sample_size, replace=False)
    else:
        indices = np.arange(total)

    model = KMeans(
        n_clusters=kmeans.k,
        random_state=kmeans.random_state,
        n_init=kmeans.n_init,
        max_iter=kmeans.max_iter,
    )
    # A low-colour image may have fewer distinct colours than k; the empty
    # clusters are handled below and are not an error.
    with warnings_module.catch_warnings():
        warnings_module.simplefilter("ignore", ConvergenceWarning)
        model.fit(pixels[indices].astype(np.float32))
    labels = model.predict(pixels.astype(np.float32)).reshape(height, width)

    mask = np.zeros((height, width), dtype=np.uint8)
    for cluster_index in range(kmeans.k):
        cluster = labels == cluster_index
        count = int(cluster.sum())
        if count == 0:
            continue

        blue, green, red = model.cluster_centers_[cluster_index]
        centroid_hsv = cv2.cvtColor(
            np.uint8([[[blue, green, red]]]), cv2.COLOR_BGR2HSV
        )[0, 0]
        saturation = float(centroid_hsv[1])

        # Saturation alone: paper is near-neutral even when it has a warm cast,
        # while green/yellow/brown tissue is strongly saturated.
        if saturation >= kmeans.min_cluster_saturation:
            mask[cluster] = 255

    return mask


def remove_small_components(mask: np.ndarray, min_area_fraction: float) -> np.ndarray:
    if min_area_fraction <= 0:
        return mask
    total = mask.shape[0] * mask.shape[1]
    min_area = max(1, int(round(min_area_fraction * total)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cleaned = mask.copy()
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < min_area:
            cleaned[labels == label] = 0
    return cleaned


def clean_mask(mask: np.ndarray, settings: LeafSettings) -> np.ndarray:
    morphology = settings.morphology
    if morphology.open_iterations:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (morphology.open_kernel, morphology.open_kernel)
        )
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, kernel, iterations=morphology.open_iterations
        )
    if morphology.close_iterations:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (morphology.close_kernel, morphology.close_kernel)
        )
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, kernel, iterations=morphology.close_iterations
        )
    return remove_small_components(mask, morphology.min_component_area_fraction)


def _contour_border_touch(
    contour: np.ndarray, width: int, height: int, band: int
) -> float:
    if band <= 0:
        return 0.0
    points = contour.reshape(-1, 2)
    if points.size == 0:
        return 0.0
    touches = (
        (points[:, 0] < band)
        | (points[:, 0] >= width - band)
        | (points[:, 1] < band)
        | (points[:, 1] >= height - band)
    )
    return float(touches.mean())


def score_candidates(mask: np.ndarray, settings: LeafSettings) -> list[LeafCandidate]:
    """Score external contours by area, fill, centrality and border contact."""
    height, width = mask.shape[:2]
    image_area = float(height * width)
    diagonal = float(np.hypot(height, width))
    candidate_settings = settings.candidate

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[LeafCandidate] = []

    for contour in contours:
        area = float(cv2.contourArea(contour))
        area_fraction = area / image_area
        if area_fraction < candidate_settings.min_area_fraction:
            continue

        hull = cv2.convexHull(contour)
        hull_area = float(cv2.contourArea(hull))
        fill_ratio = area / hull_area if hull_area > 0 else 0.0
        if fill_ratio < candidate_settings.min_fill_ratio:
            continue

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        centroid_x = moments["m10"] / moments["m00"]
        centroid_y = moments["m01"] / moments["m00"]
        offset = np.hypot(centroid_x - width / 2, centroid_y - height / 2)
        centrality = max(0.0, 1.0 - offset / (0.5 * diagonal))

        border_touch = _contour_border_touch(
            contour, width, height, candidate_settings.border_touch_band_px
        )
        score = (
            area_fraction
            * (1.0 + candidate_settings.centrality_weight * centrality)
            * (1.0 - candidate_settings.border_penalty * border_touch)
        )

        candidates.append(
            LeafCandidate(
                contour=contour,
                area=area,
                area_fraction=area_fraction,
                bbox=cv2.boundingRect(contour),
                centroid=(centroid_x, centroid_y),
                fill_ratio=fill_ratio,
                centrality=centrality,
                border_touch=border_touch,
                score=score,
            )
        )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates


def _candidate_mask(shape: tuple[int, int], candidate: LeafCandidate) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.drawContours(mask, [candidate.contour], -1, 255, thickness=cv2.FILLED)
    return mask


def segment_leaf(bgr: np.ndarray, config: SegmentationConfig) -> LeafSegmentationResult:
    """Segment the primary leaf; never raises for an ordinary non-leaf image."""
    height, width = bgr.shape[:2]
    settings = config.leaf

    colour_mask, green_mask = build_colour_mask(bgr, settings)
    kmeans_mask = build_kmeans_mask(bgr, settings)
    combined = cv2.bitwise_or(colour_mask, kmeans_mask)
    combined = clean_mask(combined, settings)

    candidates = score_candidates(combined, settings)
    green_fraction = float((green_mask > 0).mean())

    warnings: list[str] = []
    fallback = settings.fallback
    use_fallback = False
    if fallback.enabled and green_fraction >= fallback.leaf_green_fraction_threshold:
        if (
            not candidates
            or candidates[0].area_fraction >= fallback.candidate_area_fraction_for_full_frame
        ):
            use_fallback = True

    if use_fallback:
        mask = np.full((height, width), 255, dtype=np.uint8)
        warnings.append("FULL_FRAME_FALLBACK")
        return LeafSegmentationResult(
            found=True,
            mask=mask,
            bbox=(0, 0, width, height),
            area_fraction=1.0,
            fill_ratio=1.0,
            used_full_frame_fallback=True,
            multiple_leaves=False,
            candidate_count=len(candidates),
            method="full_frame_fallback",
            warnings=tuple(warnings),
        )

    if not candidates:
        return LeafSegmentationResult(
            found=False,
            mask=None,
            bbox=None,
            area_fraction=0.0,
            fill_ratio=0.0,
            used_full_frame_fallback=False,
            multiple_leaves=False,
            candidate_count=0,
            method="colour_kmeans_morphology",
            failure_reason="NO_CLEAR_LEAF_FOUND",
        )

    primary = candidates[0]
    mask = _candidate_mask((height, width), primary)

    multiple_leaves = False
    multi = settings.multi_leaf
    if multi.enabled and len(candidates) > 1:
        diagonal = float(np.hypot(height, width))
        for candidate in candidates[1:]:
            if candidate.area < multi.secondary_area_ratio * primary.area:
                continue
            if candidate.centrality < multi.secondary_centrality_min:
                continue
            distance = float(
                np.hypot(
                    candidate.centroid[0] - primary.centroid[0],
                    candidate.centroid[1] - primary.centroid[1],
                )
            )
            if distance >= multi.secondary_centroid_distance_ratio * diagonal:
                multiple_leaves = True
                break

    if multiple_leaves:
        warnings.append("MULTIPLE_LEAVES")

    return LeafSegmentationResult(
        found=True,
        mask=mask,
        bbox=primary.bbox,
        area_fraction=float((mask > 0).mean()),
        fill_ratio=primary.fill_ratio,
        used_full_frame_fallback=False,
        multiple_leaves=multiple_leaves,
        candidate_count=len(candidates),
        method="colour_kmeans_morphology",
        warnings=tuple(warnings),
    )
