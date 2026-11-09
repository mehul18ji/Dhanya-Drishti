import path from 'node:path'

import { defineConfig, devices } from '@playwright/test'

// Resolve TypeScript imports from the frontend source tree.
const frontendTsconfig = path.join(path.resolve(__dirname, '..', '..'), 'frontend', 'tsconfig.json')

/**
 * Phase 6 cross-stack browser harness.
 *
 * Two real browsers are exercised (installed Chrome and Edge channels) against
 * the real backend and either the Vite dev server (this file) or the built
 * production preview (`playwright.preview.config.ts`). Individual specs use
 * route interception for deterministic UI states and the live backend for
 * upload -> result -> artifact -> history -> clear history.
 */
const repoRoot = path.resolve(__dirname, '..', '..')
const frontendDir = path.join(repoRoot, 'frontend')
const backendDir = path.join(repoRoot, 'backend')
const runtimeDir = path.join(backendDir, '.runtime-e2e')

const apiURL = 'http://127.0.0.1:8000'
const baseURL = 'http://127.0.0.1:5173'
const python = process.env.PYTHON || 'python'

export default defineConfig({
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
    ['html', { outputFolder: path.join(__dirname, 'playwright-report'), open: 'never' }],
  ],
  outputDir: path.join(__dirname, 'test-results'),
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
      name: 'chrome',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
    {
      name: 'edge',
      use: { ...devices['Desktop Chrome'], channel: 'msedge' },
    },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: backendDir,
      url: `${apiURL}/api/v1/health`,
      timeout: 120_000,
      // Never reuse a listener here. Reuse silently kept whichever backend was already
      // on :8000 (with its own RUNTIME_DIR), which made the local-acceptance "restart"
      // check read the old process's history instead of proving startup cleanup.
      reuseExistingServer: false,
      env: {
        ...process.env,
        ENVIRONMENT: 'e2e',
        RUNTIME_DIR: runtimeDir,
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      cwd: frontendDir,
      url: baseURL,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiURL,
      },
    },
  ],
})
