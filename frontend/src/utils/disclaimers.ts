/** Fixed academic disclaimers (PRD §3, §11, §12, §28). */

export const GENERAL_DISCLAIMER =
  'This prototype supports only three diseased rice-leaf categories: Bacterial Leaf Blight, Brown Spot and Leaf Smut. Do not upload healthy leaves. Results are academic estimates and should not be used as professional agricultural advice.'

export const HEALTHY_CAVEAT =
  'There is no healthy-leaf class. The system cannot diagnose a leaf as healthy; an unusual or unsupported image should be treated as uncertain or rejected, never as a healthy result.'

export const UNCERTAIN_NOTICE =
  'This image does not closely match the disease patterns represented in the current training dataset. It may be healthy, unsupported, or unsuitable for analysis. Please upload one clear diseased rice leaf.'

export const SEVERITY_DISCLAIMER =
  'Severity is an experimental estimate based on the visible lesion area in this image. It is not a validated agronomic severity grade.'

export const SCORE_DISCLAIMER =
  'Model scores are decision-function margins, not calibrated probabilities. They must not be read as a confidence percentage.'

export const TEMPORARY_STORAGE_NOTICE =
  'History, uploaded images and diagnostic masks are temporary. They are deleted at backend restart, after the configured expiry period, or when history is cleared.'

/** Provenance of the approved 120-image dataset used for Version 1. */
export const DATASET_SOURCE_URL =
  'https://www.kaggle.com/datasets/vbookshelf/rice-leaf-diseases/data'

export const DATASET_SOURCE_NAME = 'Rice Leaf Diseases — vbookshelf (Kaggle)'

export const SMARTPHONE_CAVEAT =
  'No smartphone or field-camera validation has been performed. Segmentation thresholds were tuned on plain white-background studio images, so cluttered phone backgrounds, outdoor lighting and field conditions are untested and may produce unreliable measurements.'
