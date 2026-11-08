import { describe, expect, it } from 'vitest'

import { lesionAreaDisplay, severityDisplay } from './measurements'

describe('honest lesion and severity display', () => {
  it('never turns a missing lesion area into 0%', () => {
    const display = lesionAreaDisplay(null, true)
    expect(display.available).toBe(false)
    expect(display.text).toBe('Not available')
    expect(display.text).not.toContain('0')
  })

  it('never turns an unreliable lesion area into 0%', () => {
    const display = lesionAreaDisplay(12.4, false)
    expect(display.available).toBe(false)
    expect(display.text).not.toContain('0.0%')
    expect(display.note).toMatch(/not reliable/i)
  })

  it('keeps a measured zero honest', () => {
    const display = lesionAreaDisplay(0, true)
    expect(display.available).toBe(true)
    expect(display.text).toBe('0.0%')
  })

  it('refuses a severity bucket when lesion data is unreliable', () => {
    const display = severityDisplay('Mild', false, 'Lesion estimate unreliable.')
    expect(display.available).toBe(false)
    expect(display.text).toBe('Not reported')
    expect(display.note).toBe('Lesion estimate unreliable.')
  })

  it('shows a severity only when the backend supplied one and the lesion is reliable', () => {
    expect(severityDisplay('Moderate', true, 'n/a')).toMatchObject({
      available: true,
      text: 'Moderate',
    })
    expect(severityDisplay(null, true, 'No measurement.').available).toBe(false)
  })
})
