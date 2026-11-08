/**
 * Plain-language warning and rejection text.
 *
 * Codes are stable backend identifiers; the strings mirror
 * `backend/app/vision/messages.py` and `backend/app/vision/severity.py`. The
 * backend repeats the same text for a 200 rejection, so the code map is only a
 * safe fallback for history rows and future codes.
 */

export const WARNING_MESSAGES: Record<string, string> = {
  MULTIPLE_LEAVES:
    'Multiple leaf regions were detected. Analysis is based on the primary detected leaf. For best accuracy, upload a photograph containing one clear leaf.',
  FULL_FRAME_FALLBACK:
    'The leaf fills most of the frame, so the entire image was analysed as leaf tissue.',
  WEAK_LEAF_MASK:
    'The leaf outline was difficult to separate from the background; the area measurements may be less reliable.',
  NO_CLEAR_LEAF_FOUND:
    'No suitable rice leaf region could be detected. Upload one clear, well-lit leaf.',
  LEAF_TOO_SMALL:
    'The detected leaf region is too small for reliable analysis. Move closer to the leaf and try again.',
  SMALL_LEAF_REGION:
    'The detected leaf region is small; fine lesion detail may be lost.',
  VERY_SMALL_IMAGE:
    'The image is too small for reliable analysis. Upload a higher-resolution photograph.',
  SMALL_IMAGE: 'The image is small; fine lesion detail may be lost.',
  VERY_DARK_IMAGE:
    'The image is too dark for reliable analysis. Increase the lighting and try again.',
  DARK_IMAGE:
    'The image is darker than recommended; lesion colours may be less reliable.',
  OVEREXPOSED_IMAGE:
    'The image is over-exposed; some lesion detail may be washed out.',
  BRIGHT_IMAGE: 'The image is very bright; some lesion detail may be washed out.',
  LOW_CONTRAST:
    'The image has very low contrast, so the leaf cannot be separated reliably.',
  VERY_BLURRY_IMAGE:
    'The image is too blurry for reliable analysis. Hold the camera steady and try again.',
  BLURRY_IMAGE: 'The image appears blurry; lesion detail may be less reliable.',
  LEAF_OVEREXPOSED:
    'Part of the leaf is over-exposed; lesion colours in that region may be unreliable.',
  LEAF_UNDEREXPOSED:
    'Part of the leaf is in deep shadow; lesion colours in that region may be unreliable.',
  WEAK_LESION_MASK:
    'The detected lesion region covers an unusually large part of the leaf; the lesion-area estimate may be unreliable.',
  LESION_REFERENCE_UNAVAILABLE:
    'The leaf has almost no healthy green tissue left to compare against, so the lesion-area estimate could not be calibrated. Treat the severity estimate as unreliable.',
}

export const SEVERITY_REASON_MESSAGES: Record<string, string> = {
  LESION_ESTIMATE_UNRELIABLE:
    'Severity was not reported because the lesion-area estimate was unreliable.',
  LESION_AREA_MISSING:
    'Severity was not reported because no lesion area could be measured.',
  LESION_AREA_INVALID:
    'Severity was not reported because the lesion-area measurement was invalid.',
}

export const REJECTION_GUIDANCE: Record<string, string> = {
  NO_CLEAR_LEAF_FOUND:
    'Use one clear, well-lit rice leaf with the diseased region visible and the leaf filling a reasonable part of the frame.',
  LEAF_TOO_SMALL:
    'Move closer to the leaf, keep it in focus, and avoid extreme distance.',
  VERY_SMALL_IMAGE:
    'Upload a larger photograph; the short side of the image is too small for reliable analysis.',
  VERY_DARK_IMAGE:
    'Increase the lighting, avoid deep shadows, and try again.',
  LOW_CONTRAST:
    'Use an evenly lit photograph with the leaf clearly separated from the background.',
  VERY_BLURRY_IMAGE:
    'Hold the camera steady, wait for focus, and try again.',
}

function humaniseCode(code: string): string {
  return code
    .toLowerCase()
    .replace(/_+/g, ' ')
    .replace(/^\w/, (letter) => letter.toUpperCase())
}

export function warningMessage(code: string): string {
  return WARNING_MESSAGES[code] ?? humaniseCode(code)
}

export function severityReasonMessage(code: string | null | undefined): string {
  if (!code) return 'Severity is not available for this image.'
  return SEVERITY_REASON_MESSAGES[code] ?? humaniseCode(code)
}

export function rejectionGuidance(code: string): string {
  return (
    REJECTION_GUIDANCE[code] ??
    'Try a single, clear, well-lit rice-leaf photograph with the diseased area visible.'
  )
}
