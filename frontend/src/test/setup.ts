import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

let objectUrlCounter = 0

Object.defineProperty(URL, 'createObjectURL', {
  writable: true,
  value: vi.fn(() => {
    objectUrlCounter += 1
    return `blob:dhanyadrishti-test-${objectUrlCounter}`
  }),
})

Object.defineProperty(URL, 'revokeObjectURL', {
  writable: true,
  value: vi.fn(),
})

// jsdom does not implement scrolling; the real browser does.
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  writable: true,
  value: vi.fn(),
})
