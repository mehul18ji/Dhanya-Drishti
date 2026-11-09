import { expect, test, type Route } from '@playwright/test'

import {
  makeHealth,
  makeHistoryItem,
  makeHistoryList,
  makeModelInfo,
  makePrediction,
} from './fixtures/api'
import { chooseFile, LANDSCAPE } from './helpers/files'

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('hosted-service resilience', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

  test('the model card recovers automatically while the backend wakes', async ({ page }) => {
    await page.route('**/api/v1/health', (route) => json(route, makeHealth()))

    let calls = 0
    await page.route('**/api/v1/model-info', async (route) => {
      calls += 1
      if (calls === 1) {
        await route.abort('failed')
        return
      }
      if (calls === 2) {
        // A sleeping Render instance or proxy usually answers with HTML, not JSON.
        await route.fulfill({
          status: 503,
          contentType: 'text/html',
          body: '<html><body>Service Unavailable</body></html>',
        })
        return
      }
      await json(route, makeModelInfo())
    })

    await page.goto('/about')
    await expect(page.getByTestId('model-info-error')).toBeVisible()
    await expect(page.getByTestId('auto-retry-hint')).toContainText(/retrying automatically/i)

    // Backoff is 4 s then 8 s; no Retry click is involved.
    await expect(page.getByTestId('model-info')).toBeVisible({ timeout: 25_000 })
    expect(calls).toBeGreaterThanOrEqual(3)
    await expect(page.getByRole('heading', { name: /support vector machine/i })).toBeVisible()
  })

  test('history loads by itself after a cold-start failure', async ({ page }) => {
    await page.route('**/api/v1/health', (route) => json(route, makeHealth()))

    let calls = 0
    await page.route(/\/api\/v1\/history(?:\?.*)?$/, async (route) => {
      calls += 1
      // Development StrictMode aborts the first effect's request; fail the next
      // surviving attempt too so the automatic retry (not StrictMode) recovers.
      if (calls <= 2) {
        await route.abort('failed')
        return
      }
      await json(route, makeHistoryList([makeHistoryItem()]))
    })

    await page.goto('/history')
    await expect(page.getByTestId('history-error')).toBeVisible()
    await expect(page.getByTestId('auto-retry-hint')).toBeVisible()
    // At phone width the desktop table row is hidden; the card is the visible record.
    await expect(page.getByTestId('history-card')).toBeVisible({ timeout: 20_000 })
    expect(calls).toBeGreaterThanOrEqual(2)
  })

  test('an expired artifact shows a readable fallback, not a broken image', async ({ page }) => {
    await page.route('**/api/v1/health', (route) => json(route, makeHealth()))
    await page.route('**/api/v1/predict', (route) => json(route, makePrediction()))
    await page.route(
      /\/api\/v1\/history\/[^/]+\/(?:original|leaf-mask|lesion-mask)$/,
      (route) => route.abort('failed'),
    )

    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()
    await expect(page.getByTestId('prediction-result')).toBeVisible()

    await page.getByRole('button', { name: /preview oriented upload artifact/i }).click()
    await expect(page.getByRole('dialog', { name: /oriented upload preview/i })).toBeVisible()
    await expect(page.getByTestId('artifact-image-fallback')).toContainText(/could not be loaded/i)
    await expect(page.getByRole('button', { name: /^download$/i })).toBeEnabled()
  })
})
