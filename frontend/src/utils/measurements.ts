import type { Severity } from '../types/api'
import { formatPercent } from './format'

/**
 * Honest rendering rules for lesion area and severity.
 *
 * A missing or unreliable measurement is never turned into `0 %`, `Mild` or any
 * other bucket. A measured zero is different and stays honest: a calibrated leaf
 * with no detected lesion is displayed as `0.0%` and `Mild` (decision recorded in
 * `backend/app/vision/severity.py`).
 */

export interface LesionDisplay {
  available: boolean
  text: string
  note: string | null
}

export function lesionAreaDisplay(
  value: number | null | undefined,
  reliable: boolean,
): LesionDisplay {
  if (!reliable) {
    return {
      available: false,
      text: 'Not available',
      note: 'Lesion segmentation was not reliable, so no area is reported.',
    }
  }
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return {
      available: false,
      text: 'Not available',
      note: 'No lesion-area measurement was produced for this image.',
    }
  }
  return { available: true, text: formatPercent(value), note: null }
}

export interface SeverityDisplay {
  available: boolean
  severity: Severity | null
  text: string
  note: string | null
}

export function severityDisplay(
  severity: Severity | null | undefined,
  lesionReliable: boolean,
  reasonMessage: string,
): SeverityDisplay {
  // Defensive: never print a bucket when the underlying measurement is unreliable.
  if (!lesionReliable) {
    return {
      available: false,
      severity: null,
      text: 'Not reported',
      note: reasonMessage,
    }
  }
  if (!severity) {
    return {
      available: false,
      severity: null,
      text: 'Not reported',
      note: reasonMessage,
    }
  }
  return { available: true, severity, text: severity, note: null }
}
