import type { Page, Route } from '@playwright/test'

import type {
  HealthResponse,
  HistoryDeleteResponse,
  HistoryListResponse,
  ModelInfoResponse,
  PredictionResponse,
  RejectedResponse,
} from '../../frontend/src/types/api'
import { makeHealth } from '../fixtures/api'

/** A valid 1x1 transparent PNG, used only to satisfy artifact thumbnails. */
export const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
)

const HISTORY_PATH = /\/api\/v1\/history(?:\?.*)?$/
const ARTIFACT_PATH = /\/api\/v1\/history\/[^/]+\/(?:original|leaf-mask|lesion-mask)$/

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

export async function mockHealth(
  page: Page,
  options: {
    body?: HealthResponse
    status?: number
    offline?: boolean
    delayMs?: number
  } = {},
): Promise<void> {
  await page.route('**/api/v1/health', async (route) => {
    if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    if (options.offline) {
      await route.abort('failed')
      return
    }
    await json(route, options.body ?? makeHealth(), options.status ?? 200)
  })
}

export async function mockPredict(
  page: Page,
  body: PredictionResponse | RejectedResponse | { status: 'error'; reason_code: string; message: string },
  options: { status?: number; delayMs?: number } = {},
): Promise<void> {
  await page.route('**/api/v1/predict', async (route) => {
    if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    await json(route, body, options.status ?? 200)
  })
}

export async function mockPredictAbort(page: Page): Promise<void> {
  await page.route('**/api/v1/predict', (route) => route.abort('failed'))
}

export async function mockHistory(
  page: Page,
  list: HistoryListResponse,
  options: {
    deleteResponse?: HistoryDeleteResponse
    deleteStatus?: number
    getStatus?: number
    getDelayMs?: number
  } = {},
): Promise<void> {
  await page.route(HISTORY_PATH, async (route) => {
    const request = route.request()
    if (request.method() === 'DELETE') {
      await json(
        route,
        options.deleteResponse ?? { deleted: list.count, runtime_storage: 'temporary' },
        options.deleteStatus ?? 200,
      )
      return
    }
    if (options.getDelayMs) {
      await new Promise((resolve) => setTimeout(resolve, options.getDelayMs))
    }
    await json(route, list, options.getStatus ?? 200)
  })
}

export async function mockArtifacts(page: Page): Promise<void> {
  await page.route(ARTIFACT_PATH, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: ONE_PIXEL_PNG,
    })
  })
}

export async function mockModelInfo(
  page: Page,
  body: ModelInfoResponse,
  options: { status?: number; delayMs?: number } = {},
): Promise<void> {
  await page.route('**/api/v1/model-info', async (route) => {
    if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    await json(route, body, options.status ?? 200)
  })
}
