"""Experimental severity estimate (Phase 4 M5, PRD §12).

Version 1 severity is **not** a trained diagnosis and not an agronomic grade: it
maps the measured lesion area of the detected leaf onto three buckets. Every
threshold, label and disclaimer string is read from
:data:`backend/configs/severity.yaml` (`severity-v1`) and hashed exactly like the
Phase 2 ``seg-v2`` / ``quality-v1`` configurations, so a report can state which
configuration produced a grade.

Locked buckets (PRD §12), inclusive on the lower edge:

===============  ==========
lesion area      severity
===============  ==========
< 10 %           Mild
10 % to < 25 %   Moderate
>= 25 %          Severe
===============  ==========

Honesty rules (the reason this module exists instead of a one-line ``if``):

* an **unreliable** lesion estimate (``lesion_reliable`` false, or a
  ``LESION_REFERENCE_UNAVAILABLE`` warning) → severity ``None``;
* a **missing** lesion area → severity ``None``;
* an **invalid** lesion area (NaN, infinite, negative, above 100) → severity
  ``None``.

None of those cases may ever become ``Mild``, ``0 %`` or ``Healthy``. A *measured*
zero is different and stays honest: a calibrated leaf with no detected lesion is
``Mild`` at 0.0 %.

Every returned result carries the PRD §12 disclaimer verbatim, plus the severity
config version and SHA-256.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal, Sequence, cast

from app.vision.config import SeverityConfig, load_severity_config

SeverityLabel = Literal["Mild", "Moderate", "Severe"]

#: Why a severity is unavailable. Stable codes, safe to log or expose.
REASON_UNRELIABLE: Final[str] = "LESION_ESTIMATE_UNRELIABLE"
REASON_MISSING: Final[str] = "LESION_AREA_MISSING"
REASON_INVALID: Final[str] = "LESION_AREA_INVALID"

#: The Phase 2 warning that means the lesion estimate could not be calibrated.
UNRELIABLE_WARNING: Final[str] = "LESION_REFERENCE_UNAVAILABLE"


@dataclass(frozen=True)
class SeverityResult:
    """One severity decision, or an explicit "cannot say" with its reason."""

    severity: SeverityLabel | None
    lesion_area_percentage: float | None
    method: str
    disclaimer: str
    short_note: str
    config_version: str
    config_sha256: str
    reason_code: str | None = None

    @property
    def available(self) -> bool:
        """True only when a real bucket was assigned from a reliable measurement."""
        return self.severity is not None


def _bucket(area: float, config: SeverityConfig) -> SeverityLabel:
    """Map a validated lesion-area percentage onto the configured buckets."""
    thresholds = config.thresholds
    if area < thresholds.mild_max_percent:
        return cast(SeverityLabel, config.labels.mild)
    if area < thresholds.moderate_max_percent:
        return cast(SeverityLabel, config.labels.moderate)
    return cast(SeverityLabel, config.labels.severe)


def _unavailable(
    config: SeverityConfig,
    reason_code: str,
    *,
    area: float | None,
) -> SeverityResult:
    return SeverityResult(
        severity=None,
        lesion_area_percentage=area,
        method=config.severity_method,
        disclaimer=config.disclaimer,
        short_note=config.short_note,
        config_version=config.severity_config_version,
        config_sha256=config.content_sha256,
        reason_code=reason_code,
    )


def _valid_area(area: float) -> bool:
    """A lesion area is a percentage: finite and inside ``0..100``."""
    if isinstance(area, bool):  # bool is an int subclass; never a measurement
        return False
    try:
        value = float(area)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False
    return math.isfinite(value) and 0.0 <= value <= 100.0


def severity_for(
    lesion_area_percentage: float | None,
    *,
    lesion_reliable: bool = True,
    warnings: Sequence[str] = (),
    config: SeverityConfig | None = None,
) -> SeverityResult:
    """Classify one lesion-area measurement, refusing to guess when it is unusable.

    ``lesion_reliable`` and ``warnings`` come straight from the Phase 2/3 result
    (``PreprocessingOutcome.lesion_reliable`` / ``.warnings``): a result flagged
    unreliable there must never produce a Mild/Moderate/Severe label.
    """
    resolved = config or load_severity_config()
    warning_codes = set(warnings)

    if not lesion_reliable or UNRELIABLE_WARNING in warning_codes:
        return _unavailable(
            resolved, REASON_UNRELIABLE, area=lesion_area_percentage
        )

    if lesion_area_percentage is None:
        return _unavailable(resolved, REASON_MISSING, area=None)

    if not _valid_area(lesion_area_percentage):
        return _unavailable(
            resolved, REASON_INVALID, area=lesion_area_percentage
        )

    area = float(lesion_area_percentage)
    return SeverityResult(
        severity=_bucket(area, resolved),
        lesion_area_percentage=area,
        method=resolved.severity_method,
        disclaimer=resolved.disclaimer,
        short_note=resolved.short_note,
        config_version=resolved.severity_config_version,
        config_sha256=resolved.content_sha256,
        reason_code=None,
    )
