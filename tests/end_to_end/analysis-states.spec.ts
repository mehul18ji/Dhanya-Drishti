import { expect, test } from '@playwright/test'

import { SEVERITY_DISCLAIMER } from './fixtures/api'
import {
  makeHistoryList,
  makeHealth,
  makePrediction,
  makeRejected,
  makeUncertainPrediction,
} from './fixtures/api'
import { chooseFile, LANDSCAPE } from './helpers/files'
import {
  mockHealth,
  mockHistory,
  mockPredict,
  mockPredictAbort,
} from './helpers/network'

test.describe('analysis states', () => {
  test.beforeEach(async ({ page }) => {
    await mockHealth(page)
  })

  test('loading then predicted result uses margins, severity disclaimer and artifacts', async ({
    page,
  }) => {
    await mockPredict(page, makePrediction(), { delayMs: 1_200 })

    await page.goto('/')
    await expect(page.getByTestId('model-ready')).toBeVisible()

    await chooseFile(page, LANDSCAPE)
    await expect(page.getByTestId('preview-orientation')).toHaveText('Landscape')
    await page.getByRole('button', { name: 'Analyze leaf' }).click()

    await expect(page.getByTestId('analysis-progress')).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toHaveAttribute(
      'data-status',
      'predicted',
    )
    await expect(page.getByRole('heading', { name: 'Brown Spot' })).toBeVisible()
    await expect(page.getByTestId('severity-badge')).toHaveText('Moderate')
    await expect(page.getByTestId('severity-disclaimer')).toHaveText(
      SEVERITY_DISCLAIMER,
    )
    await expect(page.getByTestId('score-panel')).toContainText(
      'not probabilities or percentages',
    )
    await expect(page.getByTestId('decision-margin')).toHaveText('+1.13')
    await expect(page.getByTestId('segmentation-preview')).toBeVisible()
    await expect(page.locator('body')).not.toContainText(/\bHealthy\b/)
    await expect(page.getByTestId('confidence')).toHaveCount(0)
  })

  test('uncertain result keeps unreliable lesions unavailable and shows warnings', async ({
    page,
  }) => {
    await mockPredict(page, makeUncertainPrediction())

    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()

    await expect(page.getByTestId('prediction-result')).toHaveAttribute(
      'data-status',
      'uncertain',
    )
    await expect(page.getByText('Unconfirmed pattern — this is not a diagnosis.')).toBeVisible()
    await expect(page.getByText('Uncertain result — treat the label as unconfirmed')).toBeVisible()
    await expect(page.getByTestId('severity-badge')).toHaveText('Not reported')
    await expect(
      page.getByText('Lesion segmentation was not reliable, so no area is reported.'),
    ).toBeVisible()
    await expect(
      page.getByText('Not converted to 0% and not assigned a severity bucket.'),
    ).toBeVisible()
    await expect(page.getByTestId('quality-warnings')).toContainText('LOW_CONTRAST')
    await expect(page.getByTestId('quality-warnings')).toContainText('SMALL_IMAGE')
    await expect(page.getByText('lesion_area_ratio', { exact: true })).toBeVisible()
    await expect(page.getByText('lesion_count_per_kpx', { exact: true })).toBeVisible()
    await expect(page.getByTestId('score-panel')).toContainText('decision margins')
    await expect(page.getByTestId('severity-badge')).not.toHaveText('Mild')
  })

  test('HTTP 200 rejection is not a prediction and is absent from history', async ({
    page,
  }) => {
    await mockPredict(page, makeRejected())
    await mockHistory(page, makeHistoryList([]))

    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()

    await expect(page.getByTestId('rejected-result')).toBeVisible()
    await expect(page.getByText('Image rejected — no prediction')).toBeVisible()
    await expect(page.getByText('No disease label was assigned.')).toBeVisible()
    await expect(page.getByText('This upload was not added to temporary prediction history.')).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toHaveCount(0)
    await expect(page.getByTestId('score-panel')).toHaveCount(0)
    await expect(page.getByTestId('severity-badge')).toHaveCount(0)

    await page.getByRole('link', { name: 'Prediction History' }).click()
    await expect(page.getByTestId('history-empty')).toBeVisible()
    await expect(page.getByTestId('history-row')).toHaveCount(0)
    await expect(page.getByTestId('history-count')).toHaveText('0 records')
  })

  const uploadErrors = [
    {
      name: '413 file too large',
      status: 413,
      reason: 'FILE_TOO_LARGE',
      message: 'Upload exceeds the 10 MB limit.',
      title: 'File too large',
    },
    {
      name: '415 unsupported type',
      status: 415,
      reason: 'UNSUPPORTED_FILE_TYPE',
      message: 'The upload is not a supported image type.',
      title: 'Unsupported file type',
    },
    {
      name: '422 unreadable image',
      status: 422,
      reason: 'INVALID_UPLOAD',
      message: 'The image could not be decoded.',
      title: 'Image could not be read',
    },
  ] as const

  for (const scenario of uploadErrors) {
    test(`${scenario.name} stays an upload error, not a rejection`, async ({ page }) => {
      await mockPredict(
        page,
        {
          status: 'error',
          reason_code: scenario.reason,
          message: scenario.message,
        },
        { status: scenario.status },
      )

      await page.goto('/')
      await chooseFile(page, LANDSCAPE)
      await page.getByRole('button', { name: 'Analyze leaf' }).click()

      await expect(page.getByTestId('analysis-error')).toBeVisible()
      await expect(page.getByText(scenario.title).first()).toBeVisible()
      await expect(page.getByTestId('analysis-error')).toContainText(
        'not a disease result',
      )
      await expect(page.getByTestId('prediction-result')).toHaveCount(0)
      await expect(page.getByTestId('rejected-result')).toHaveCount(0)
    })
  }

  test('503 model-unavailable is a retryable service error', async ({ page }) => {
    await mockPredict(
      page,
      {
        status: 'error',
        reason_code: 'MODEL_NOT_LOADED',
        message: 'Production model not loaded.',
      },
      { status: 503 },
    )

    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()

    await expect(page.getByTestId('analysis-error')).toBeVisible()
    await expect(page.getByText('Analysis service is starting…').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toHaveCount(0)
    await expect(page.getByTestId('rejected-result')).toHaveCount(0)
  })

  test('backend offline disables analysis and explains the connection failure', async ({
    page,
  }) => {
    await page.unroute('**/api/v1/health')
    await mockHealth(page, { offline: true })

    await page.goto('/')
    await expect(page.getByTestId('backend-unavailable')).toBeVisible()
    await chooseFile(page, LANDSCAPE)
    await expect(page.getByTestId('preview-orientation')).toHaveText('Landscape')
    await expect(page.getByRole('button', { name: 'Analyze leaf' })).toBeDisabled()
    await expect(page.getByTestId('backend-unavailable')).toContainText(
      'Could not reach the backend',
    )
  })

  test('backend online with model starting disables analysis without pretending success', async ({
    page,
  }) => {
    await page.unroute('**/api/v1/health')
    await mockHealth(page, { body: { ...makeHealth(), model_loaded: false } })

    await page.goto('/')
    await expect(page.getByTestId('model-unavailable')).toBeVisible()
    await chooseFile(page, LANDSCAPE)
    await expect(page.getByRole('button', { name: 'Analyze leaf' })).toBeDisabled()
    await expect(page.getByTestId('model-ready')).toHaveCount(0)
  })

  test('network failure during analysis is shown as a service error', async ({ page }) => {
    await mockPredictAbort(page)

    await page.goto('/')
    await chooseFile(page, LANDSCAPE)
    await page.getByRole('button', { name: 'Analyze leaf' }).click()

    await expect(page.getByTestId('analysis-error')).toBeVisible()
    await expect(page.getByText('Starting analysis service…').first()).toBeVisible()
    await expect(page.getByTestId('prediction-result')).toHaveCount(0)
  })
})
