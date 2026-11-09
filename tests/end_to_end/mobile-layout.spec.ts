import { Buffer } from 'node:buffer'

import { expect, test } from '@playwright/test'

import { makePrediction } from './fixtures/api'
import { chooseFile, LANDSCAPE } from './helpers/files'
import { mockHealth, mockHistory, mockPredict } from './helpers/network'

// Smallest common phone width; catches horizontal overflow and tiny tap targets.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

// 1x1 transparent PNG so the mocked artifacts load without touching the backend.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
)

test.describe('phone layout', () => {
  test.beforeEach(async ({ page }) => {
    await mockHealth(page)
    await mockHistory(page, { count: 0, items: [], runtime_storage: 'temporary' })
    await page.route('**/api/v1/history/**', (route) =>
      route.fulfill({ status: 200, contentType: 'image/png', body: PNG }),
    )
  })

  test('every page fits a 390px viewport without horizontal scrolling', async ({ page }) => {
    for (const path of ['/', '/history', '/about']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, `${path} overflows horizontally by ${overflow}px`).toBeLessThanOrEqual(1)
    }
  })

  test('tapping anywhere in the dashed upload area opens the file picker', async ({ page }) => {
    await page.goto('/')

    const chooserPromise = page.waitForEvent('filechooser')
    await page.getByTestId('upload-dropzone').click({ position: { x: 18, y: 18 } })
    const chooser = await chooserPromise
    await chooser.setFiles(LANDSCAPE)

    await expect(page.getByTestId('image-preview')).toBeVisible()
    await expect(page.getByTestId('preview-orientation')).toHaveText('Landscape')
  })

  test('artifact tap previews full screen; only Download saves the PNG', async ({ page }) => {
    await mockPredict(page, makePrediction())
    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()
    await expect(page.getByTestId('prediction-result')).toBeVisible()

    const unexpectedDownload = page
      .waitForEvent('download', { timeout: 1_500 })
      .then(() => true)
      .catch(() => false)

    await page.getByRole('button', { name: /preview oriented upload artifact/i }).click()
    const dialog = page.getByRole('dialog', { name: /oriented upload preview/i })
    await expect(dialog).toBeVisible()
    await expect(page.getByTestId('artifact-full-image')).toBeVisible()
    expect(await unexpectedDownload).toBe(false)

    const downloadPromise = page.waitForEvent('download')
    await dialog.getByRole('button', { name: /^download$/i }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('oriented-upload.png')

    await dialog.getByRole('button', { name: /close preview/i }).click()
    await expect(dialog).toBeHidden()
  })
})
