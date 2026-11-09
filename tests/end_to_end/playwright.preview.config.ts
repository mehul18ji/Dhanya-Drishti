import path from 'node:path'

import { defineConfig, devices } from '@playwright/test'

// Import the shared Playwright config options (workers, timeouts, reporters, etc.).
import sharedConfig from './playwright.config.js'

// Resolve TypeScript imports from the frontend source tree.
const frontendTsconfig = path.join(path.resolve(__dirname, '..', '..'), 'frontend', 'tsconfig.json')

/**
 * Production-preview browser check (Phase 6).
 *
 * Builds the real Vite bundle with the E2E API base, then serves it through
 * `vite preview` and runs the same specs. This catches asset/route/fallback
 * problems that a dev-server-only suite would miss.
 */
const repoRoot = path.resolve(__dirname, '..', '..')
const frontendDir = path.join(repoRoot, 'frontend')
const backendDir = path.join(repoRoot, 'backend')
const runtimeDir = path.join(backendDir, '.runtime-e2e-preview')

const apiURL = 'http://127.0.0.1:8000'
const baseURL = 'http://127.0.0.1:5173'
const python = process.env.PYTHON || 'python'

export default defineConfig({
  ...sharedConfig,
  tsconfig: frontendTsconfig,
  testDir: __dirname,
  testIgnore: ['**/playwright.*.config.ts'],
  timeout: 75_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(__dirname, 'playwright-preview-report'), open: 'never' }],
  ],
  outputDir: path.join(__dirname, 'test-results-preview'),
  use: {
    baseURL,
    actionTimeout: 12_000,
    navigationTimeout: 45_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chrome-preview',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: backendDir,
      url: `${apiURL}/api/v1/health`,
      timeout: 120_000,
      // Own the backend process: a reused listener would keep its previous
      // RUNTIME_DIR and invalidate any temporary-storage/restart assertion.
      reuseExistingServer: false,
      env: {
        ...process.env,
        ENVIRONMENT: 'e2e-preview',
        RUNTIME_DIR: runtimeDir,
      },
    },
    {
      command:
        'npm run build && npm run preview -- --host 127.0.0.1 --port 5173 --strictPort',
      cwd: frontendDir,
      url: baseURL,
      timeout: 240_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiURL,
      },
    },
  ],
})
