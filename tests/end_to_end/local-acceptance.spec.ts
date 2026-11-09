import { existsSync } from 'node:fs'
import path from 'node:path'

import { expect, test } from '@playwright/test'

/**
 * Real-browser local acceptance (no route interception).
 *
 * Uploads one fixed held-out dataset image through the actual dashboard, the real
 * backend, the real segmentation/feature pipeline and the committed svm-v1.0.0
 * bundle, then checks the result, artifacts, temporary history and clear-history
 * behaviour. Also fails on any console error, page error, failed request or 5xx.
 *
 * The image is read in place from the git-ignored raw dataset (never copied or
 * committed). The raw dataset is required, so the test skips on a clean clone.
 */
const repoRoot = path.resolve(__dirname, '..', '..')
const heldOutImage = path.join(
  repoRoot,
  'data',
  'raw',
  'rice_leaf_diseases',
  'Bacterial leaf blight',
  'DSC_0367.JPG',
)
const THREE_CLASSES = ['bacterial_leaf_blight', 'brown_spot', 'leaf_smut']
const DISEASE_NAMES: Record<string, string> = {
  bacterial_leaf_blight: 'Bacterial Leaf Blight',
  brown_spot: 'Brown Spot',
  leaf_smut: 'Leaf Smut',
}

test.describe('real localhost acceptance (live backend)', () => {
  test.skip(
    !existsSync(heldOutImage),
    'held-out dataset image is absent (data/raw is git-ignored); run on a machine with the approved dataset',
  )

  test('browser upload -> real API -> result, artifacts, history, clear history', async ({
    page,
  }) => {
    const consoleErrors: string[] = []
    const ignoredConsoleErrors: string[] = []
    const pageErrors: string[] = []
    const failedRequests: string[] = []
    const abortedRequests: string[] = []
    const badResponses: string[] = []
    const notFoundResponses: string[] = []

    page.on('response', (response) => {
      if (response.status() === 404) notFoundResponses.push(response.url())
    })

    page.on('console', (message) => {
      if (message.type() !== 'error') return
      const entry = `${message.text()} @ ${message.location().url || '(no url)'}`
      // The browser always requests /favicon.ico; the Vite dev server has no such
      // asset. Documented cosmetic 404, not an application error.
      if (message.location().url.endsWith('/favicon.ico')) {
        ignoredConsoleErrors.push(entry)
      } else {
        consoleErrors.push(entry)
      }
    })
    page.on('pageerror', (error) => pageErrors.push(String(error)))
    page.on('requestfailed', (request) => {
      const reason = request.failure()?.errorText ?? 'failed'
      const entry = `${request.method()} ${request.url()} -> ${reason}`
      // The app cancels in-flight health/history fetches via AbortController when a
      // component unmounts or refreshes; an abort is deliberate, not a failure.
      if (reason === 'net::ERR_ABORTED') abortedRequests.push(entry)
      else failedRequests.push(entry)
    })
    page.on('response', (response) => {
      if (response.status() >= 500) {
        badResponses.push(`${response.status()} ${response.url()}`)
      }
    })

    await page.goto('/')
    await expect(page.getByTestId('model-ready')).toBeVisible({ timeout: 60_000 })

    // -- upload through the real file input -------------------------------- #
    await page.locator('input[type="file"]').setInputFiles(heldOutImage)
    await expect(page.getByTestId('image-preview')).toBeVisible()
    await expect(page.getByTestId('preview-orientation')).toHaveText('Landscape')

    // -- real prediction --------------------------------------------------- #
    const startedAt = Date.now()
    const [response] = await Promise.all([
      page.waitForResponse(
        (candidate) =>
          candidate.url().includes('/api/v1/predict') &&
          candidate.request().method() === 'POST',
        { timeout: 120_000 },
      ),
      page.getByRole('button', { name: 'Analyze leaf' }).click(),
    ])
    const browserRoundTripMs = Date.now() - startedAt

    expect(response.status()).toBe(200)
    const body = await response.json()
    expect(body.prediction_id).toBeTruthy()
    expect(['predicted', 'uncertain']).toContain(body.status)
    expect(THREE_CLASSES).toContain(body.disease)
    expect(Object.keys(body.decision_scores).sort()).toEqual([...THREE_CLASSES].sort())
    expect(body.score_kind).toBe('decision_margin')
    expect(body).not.toHaveProperty('confidence')
    expect(body).not.toHaveProperty('probability')

    await expect(page.getByTestId('prediction-result')).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toHaveAttribute(
      'data-status',
      body.status,
    )
    await expect(page.getByTestId('score-panel')).toBeVisible()
    await expect(page.getByTestId('score-panel')).toContainText(
      'not probabilities or percentages',
    )
    await expect(page.getByTestId('severity-disclaimer')).toContainText(
      'experimental estimate',
    )
    await expect(page.getByTestId('confidence')).toHaveCount(0)
    await expect(page.locator('body')).not.toContainText(/\bHealthy\b/)

    // -- real artifact PNGs load in the browser ---------------------------- #
    const artifactImages = page.getByTestId('segmentation-preview').locator('img')
    await expect(artifactImages).toHaveCount(3)
    const loaded = await artifactImages.evaluateAll((nodes) =>
      nodes.map((node) => {
        const image = node as HTMLImageElement
        return { complete: image.complete, naturalWidth: image.naturalWidth }
      }),
    )
    expect(loaded.every((image) => image.complete && image.naturalWidth > 0)).toBe(true)

    // -- artifact tap previews; the Download button is the only download --- #
    await page.getByRole('button', { name: /preview oriented upload artifact/i }).click()
    const viewer = page.getByRole('dialog', { name: /oriented upload preview/i })
    await expect(viewer).toBeVisible()
    await expect(viewer.getByTestId('artifact-full-image')).toBeVisible()

    const [artifactDownload] = await Promise.all([
      page.waitForEvent('download'),
      viewer.getByRole('button', { name: /^download$/i }).click(),
    ])
    expect(artifactDownload.suggestedFilename()).toBe('oriented-upload.png')
    await viewer.getByRole('button', { name: /close preview/i }).click()
    await expect(viewer).toBeHidden()

    // -- temporary history ------------------------------------------------ #
    await page.getByRole('link', { name: 'Prediction History' }).click()
    await expect(page.getByTestId('history-row')).toHaveCount(1)
    await expect(page.getByTestId('history-count')).toHaveText('1 record')
    await expect(page.getByTestId('history-row')).toContainText(
      DISEASE_NAMES[body.disease as string] ?? body.disease,
    )

    // -- clear history (explicit confirmation) ----------------------------- #
    await page.getByRole('button', { name: 'Clear history' }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Clear history' }).click()

    await expect(page.getByTestId('history-empty')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('history-row')).toHaveCount(0)
    await expect(page.getByTestId('history-count')).toHaveText('0 records')

    // -- console / network health ----------------------------------------- #
    console.log(`404 responses: ${notFoundResponses.join(' | ') || '(none)'}`)
    expect(consoleErrors, `console errors: ${consoleErrors.join(' | ')}`).toEqual([])
    expect(pageErrors, `page errors: ${pageErrors.join(' | ')}`).toEqual([])
    expect(failedRequests, `failed requests: ${failedRequests.join(' | ')}`).toEqual([])
    expect(badResponses, `5xx responses: ${badResponses.join(' | ')}`).toEqual([])

    console.log(
      JSON.stringify({
        browser_round_trip_ms: browserRoundTripMs,
        status: body.status,
        disease: body.disease,
        decision_scores: body.decision_scores,
        margin: body.margin,
        severity: body.severity,
        lesion_area_percentage: body.lesion_area_percentage,
        stage_ms: body.stage_ms,
        artifacts_loaded: loaded.length,
        console_errors: consoleErrors.length,
        ignored_console_errors: ignoredConsoleErrors,
        not_found_responses: notFoundResponses,
        failed_requests: failedRequests.length,
        aborted_requests: abortedRequests.length,
      }),
    )
  })
})
