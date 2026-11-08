# DhanyaDrishti — End-to-end tests

Real-browser Playwright coverage for the analysis-state flow.

All HTTP routes are intercepted during the suite, so it never depends on a live backend for
predict/history — only the Playwright `webServer` processes run, and the browser is pointed
at mocked responses. The three fixture images exercise the frontend upload/preview path.

Three browsers are covered across two configs:
- `playwright.config.ts` -> Chrome + Edge (dev server)
- `playwright.preview.config.ts` -> Chrome (production preview)

## Prerequisites

Install browsers once (already done in this project):

```bash
cd tests/end_to_end
npx playwright install   # installs Chromium, Firefox, WebKit if missing
```

Browsers present in this project:
- Chromium at `C:\Users\jaisw\AppData\Local\ms-playwright\chromium-1254`
- Edge (system-installed, used via the `msedge` channel)

## Run

From the repository root:

```bash
# Development-server suite (backend + Vite dev server, Chrome + Edge)
cd tests/end_to_end && npx playwright test

# Production-preview suite (built bundle via `vite preview`, Chrome only)
cd tests/end_to_end && npx playwright test --config=playwright.preview.config.ts

# Headed run (opens browsers; useful for debugging)
cd tests/end_to_end && npx playwright test --headed
```

Project-specific invocations:

```bash
# Just Chrome
cd tests/end_to_end && npx playwright test --project=chrome

# Just Edge
cd tests/end_to_end && npx playwright test --project=edge

# Just the preview suite
cd tests/end_to_end && npx playwright test --config=playwright.preview.config.ts --project=chrome-preview
```

## Harness commands

Run from the repository root:

```bash
npm run test:e2e        # dev-server suite (Chrome + Edge, default config)
npm run test:e2e:headed # dev-server suite, headed
npm run test:e2e:preview # production-preview suite (Chrome, built bundle)
```

All three require browsers installed and a Node.js 20+ environment.

## What the suite covers

10 analysis-state scenarios, each asserted in both Chrome and Edge on the dev server,
and again in Chrome on the built production preview:

1. Predicted result: decision margins, severity disclaimer, artifacts, no Healthy text,
   no confidence field.
2. Uncertain result: unconfirmed notice, lesion unavailable, warnings, missing features,
   no Mild badge.
3. HTTP-200 rejection: reason, no prediction id, not in history.
4. 413 file too large: upload error, not a rejection.
5. 415 unsupported type: upload error, not a rejection.
6. 422 unreadable image: upload error, not a rejection.
7. 503 model-unavailable: retryable service error.
8. Backend offline: analysis disabled, connection-failure text.
9. Model starting: analysis disabled, no fake success.
10. Network failure during analysis: service error, not a prediction.

## Fixture images

- `fixtures/images/leaf_landscape.png` — 900×700 landscape
- `fixtures/images/leaf_portrait.png` — 700×900 portrait
- `fixtures/images/leaf_rejected.png` — 700×700 square

## Generated artifacts

Test results and reports live under `tests/end_to_end/`. They are gitignored — do not commit:

- `test-results/`, `test-results-preview/` — per-run traces, logs, screenshots (gitignored via `.gitignore`)
- `playwright-report/`, `playwright-preview-report/` — HTML reports (gitignored via `.gitignore`)
- `playwright-report/`, `playwright-preview-report/` — HTML reports
- `playwright.config.ts` output dir, `playwright.preview.config.ts` output dir (gitignored via `.gitignore`)

Uses project outputs from backend runtime dirs:
- `backend/.runtime-e2e/`, `backend/.runtime-e2e-preview/` — temporary history/artifacts dirs (created by the Playwright webServer, cleaned by the lifespan wipe)

## Cross-browser

Two browser projects are used for the dev-server suite:
- `chrome` — Desktop Chrome (channel: chrome)
- `edge` — Desktop Chrome (channel: msedge)

The production-preview suite uses a single `chrome-preview` project.
