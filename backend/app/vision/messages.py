"""Human-readable warning and rejection messages.

Codes are stable identifiers used by tests and the API; messages are what the
dashboard shows. The multiple-leaf text is mandated verbatim by PRD §7.
"""

from __future__ import annotations

WARNING_MESSAGES: dict[str, str] = {
    # Leaf detection
    "MULTIPLE_LEAVES": (
        "Multiple leaf regions were detected. Analysis is based on the primary "
        "detected leaf. For best accuracy, upload a photograph containing one clear leaf."
    ),
    "FULL_FRAME_FALLBACK": (
        "The leaf fills most of the frame, so the entire image was analysed as leaf tissue."
    ),
    "WEAK_LEAF_MASK": (
        "The leaf outline was difficult to separate from the background; "
        "the area measurements may be less reliable."
    ),
    "NO_CLEAR_LEAF_FOUND": (
        "No suitable rice leaf region could be detected. Upload one clear, well-lit leaf."
    ),
    "LEAF_TOO_SMALL": (
        "The detected leaf region is too small for reliable analysis. "
        "Move closer to the leaf and try again."
    ),
    "SMALL_LEAF_REGION": (
        "The detected leaf region is small; fine lesion detail may be lost."
    ),
    # Dimensions
    "VERY_SMALL_IMAGE": (
        "The image is too small for reliable analysis. Upload a higher-resolution photograph."
    ),
    "SMALL_IMAGE": (
        "The image is small; fine lesion detail may be lost."
    ),
    # Brightness and contrast
    "VERY_DARK_IMAGE": (
        "The image is too dark for reliable analysis. Increase the lighting and try again."
    ),
    "DARK_IMAGE": (
        "The image is darker than recommended; lesion colours may be less reliable."
    ),
    "OVEREXPOSED_IMAGE": (
        "The image is over-exposed; some lesion detail may be washed out."
    ),
    "BRIGHT_IMAGE": (
        "The image is very bright; some lesion detail may be washed out."
    ),
    "LOW_CONTRAST": (
        "The image has very low contrast, so the leaf cannot be separated reliably."
    ),
    # Blur
    "VERY_BLURRY_IMAGE": (
        "The image is too blurry for reliable analysis. Hold the camera steady and try again."
    ),
    "BLURRY_IMAGE": (
        "The image appears blurry; lesion detail may be less reliable."
    ),
    # Exposure inside the leaf mask
    "LEAF_OVEREXPOSED": (
        "Part of the leaf is over-exposed; lesion colours in that region may be unreliable."
    ),
    "LEAF_UNDEREXPOSED": (
        "Part of the leaf is in deep shadow; lesion colours in that region may be unreliable."
    ),
    # Lesion segmentation
    "WEAK_LESION_MASK": (
        "The detected lesion region covers an unusually large part of the leaf; "
        "the lesion-area estimate may be unreliable."
    ),
    "LESION_REFERENCE_UNAVAILABLE": (
        "The leaf has almost no healthy green tissue left to compare against, so the "
        "lesion-area estimate could not be calibrated. Treat the severity estimate as "
        "unreliable."
    ),
}
