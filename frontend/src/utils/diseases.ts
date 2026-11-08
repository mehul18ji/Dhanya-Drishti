/** Display names for the three supported disease slugs (PRD §2). */

export interface SupportedDisease {
  slug: string
  name: string
  summary: string
}

export const SUPPORTED_DISEASES: SupportedDisease[] = [
  {
    slug: 'bacterial_leaf_blight',
    name: 'Bacterial Leaf Blight',
    summary:
      'Water-soaked streaks that enlarge into pale, dry lesions along the leaf blade.',
  },
  {
    slug: 'brown_spot',
    name: 'Brown Spot',
    summary: 'Oval brown lesions, often with a lighter centre, scattered across the leaf.',
  },
  {
    slug: 'leaf_smut',
    name: 'Leaf Smut',
    summary: 'Small dark, slightly raised spots distributed over the leaf surface.',
  },
]

const DISEASE_NAMES: Record<string, string> = Object.fromEntries(
  SUPPORTED_DISEASES.map((disease) => [disease.slug, disease.name]),
)

function humaniseSlug(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

/**
 * Map a backend disease slug to its display name.
 *
 * The API never returns a healthy class. A defensive guard still refuses to print
 * "Healthy" if an unexpected value ever arrives, because the model cannot support
 * that claim.
 */
export function diseaseLabel(value: string | null | undefined): string {
  if (!value) return 'Unknown label'
  const normalised = value.trim().toLowerCase()
  if (!normalised) return 'Unknown label'
  if (normalised.includes('healthy') || normalised === 'healthy') {
    return 'Unsupported label'
  }
  return DISEASE_NAMES[normalised] ?? humaniseSlug(value)
}

export function isSupportedDisease(value: string | null | undefined): boolean {
  if (!value) return false
  return value.trim().toLowerCase() in DISEASE_NAMES
}
