import { describe, expect, it } from 'vitest'

import { makeFile } from '../test/fixtures'
import { validateUploadFile } from './upload'

describe('client-side upload pre-check', () => {
  it('accepts JPG, JPEG, PNG and WEBP', () => {
    for (const name of ['leaf.jpg', 'leaf.JPEG', 'leaf.png', 'leaf.webp']) {
      expect(validateUploadFile(makeFile({ name }))).toEqual({ ok: true, error: null })
    }
  })

  it('rejects unsupported extensions', () => {
    const result = validateUploadFile(makeFile({ name: 'leaf.gif', type: 'image/gif' }))
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/unsupported file type/i)
  })

  it('rejects an allowed extension with a contradictory MIME type', () => {
    const result = validateUploadFile(makeFile({ name: 'leaf.jpg', type: 'application/pdf' }))
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/unsupported image format/i)
  })

  it('rejects empty files', () => {
    const result = validateUploadFile(makeFile({ size: 0 }))
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/empty/i)
  })

  it('rejects files above the configured limit', () => {
    const result = validateUploadFile(makeFile({ size: 11 * 1024 * 1024 }), 10)
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/limit is 10 MB/i)
  })
})
