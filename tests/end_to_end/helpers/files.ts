import { readFileSync } from 'node:fs'
import path from 'node:path'

import type { Page } from '@playwright/test'

export interface UploadFixture {
  name: string
  mimeType: string
  buffer: Buffer
}

const FIXTURE_DIR = path.join(__dirname, '..', 'fixtures', 'images')

export function uploadFixture(name: string, mimeType = 'image/png'): UploadFixture {
  return {
    name,
    mimeType,
    buffer: readFileSync(path.join(FIXTURE_DIR, name)),
  }
}

export async function chooseFile(page: Page, fixture: UploadFixture): Promise<void> {
  await page.locator('input[type="file"]').setInputFiles(fixture)
}

export const LANDSCAPE = uploadFixture('leaf_landscape.png')
export const PORTRAIT = uploadFixture('leaf_portrait.png')
export const REJECTED = uploadFixture('leaf_rejected.png')
