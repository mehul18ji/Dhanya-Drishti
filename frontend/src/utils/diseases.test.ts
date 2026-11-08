import { describe, expect, it } from 'vitest'

import { diseaseLabel, isSupportedDisease } from './diseases'
import { formatScore } from './format'

describe('disease labels', () => {
  it('maps all three backend slugs to display names', () => {
    expect(diseaseLabel('bacterial_leaf_blight')).toBe('Bacterial Leaf Blight')
    expect(diseaseLabel('brown_spot')).toBe('Brown Spot')
    expect(diseaseLabel('leaf_smut')).toBe('Leaf Smut')
  })

  it('humanises unexpected slug formats without inventing support', () => {
    expect(diseaseLabel('bacterial-leaf-blight')).toBe('Bacterial Leaf Blight')
    expect(isSupportedDisease('brown_spot')).toBe(true)
    expect(isSupportedDisease('healthy')).toBe(false)
  })

  it('never renders a healthy value as a disease result', () => {
    expect(diseaseLabel('healthy')).toBe('Unsupported label')
    expect(diseaseLabel('HEALTHY_LEAF')).toBe('Unsupported label')
    expect(diseaseLabel(null)).toBe('Unknown label')
  })

  it('formats signed margins without a percent sign', () => {
    expect(formatScore(1.31)).toBe('+1.31')
    expect(formatScore(-0.42)).toBe('-0.42')
    expect(formatScore(0)).toBe('0.00')
    expect(formatScore(null)).toBe('—')
    expect(formatScore(1.31)).not.toContain('%')
  })
})
