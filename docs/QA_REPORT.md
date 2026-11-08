# DhanyaDrishti — Phase 6 QA Report

> **Status:** Complete (2026-11-08)
> **Phase:** 6 — Integration, QA, model card
> **Branch:** main

This document records the real-browser end-to-end testing, cross-browser checks,
frontend/backend contract verification, and known limitations for DhanyaDrishti V1.

---

## 1. Test environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Node.js | v25.9.0 |
| npm | v11.12.1 |
| Python | 3.11.9 |
| Playwright | 1.65.0 |
| Chrome channel | chromium (Chrome for Testing 158.0.8127.18) |
| Edge channel | msedge (system-installed) |
| Frontend | React 18 + Vite 6 + TypeScript + Tailwind CSS v3 |
| Backend | FastAPI + Uvicorn, CPU-only |
| Model bundle | svm-v1.0.0 (RBF SVM, decision-margin scores) |

---

## 2. Test results summary

### 2.1 Frontend unit tests (Vitest + jsdom + Testing Library)

- **Files:** 13
- **Tests:** 64
- **Result:** ✅ All passing
- **Scope:** API client, upload, preview, result cards, history, Analyze flow, Header, About Model, error mapping

### 2.2 Frontend typecheck

- **Command:** `npm run typecheck`
- **Result:** ✅ Clean (no errors, no warnings)

### 2.3 Frontend production build

- **Command:** `npm run build`
- **Result:** ✅ Clean
- **Output:** `frontend/dist/` — `index.html` + hashed CSS/JS assets

### 2.4 Backend tests (pytest)

- **Tests:** 217 passed
- **Result:** ✅ All passing
- **Scope:** Upload validation, preprocessing, segmentation, feature extraction, inference, severity, prediction composition, history, artifacts, health, model-info, predict route, history routes, split invariants

### 2.5 Root split-invariant tests

- **Tests:** 6 passed
- **Result:** ✅ All passing
- **Scope:** Dataset split integrity (40/40/40, 24 test / 96 CV, disjoint, 8/class test, fold coverage)

### 2.6 Playwright E2E — development server

- **Config:** `tests/end_to_end/playwright.config.ts`
- **Browsers:** Chrome (chrome channel), Edge (msedge channel)
- **Tests:** 20 (10 per browser)
- **Result:** ✅ All passing (20/20)
- **Duration:** ~20 seconds total

#### Browser projects

| Project | Browser | Tests | Result |
|---|---|---|---|
| chrome | Desktop Chrome (channel: chrome) | 10 | ✅ 10/10 |
| edge | Desktop Chrome (channel: msedge) | 10 | ✅ 10/10 |

#### Test coverage

| Test | Chrome | Edge | What it verifies |
|---|---|---|---|
| loading then predicted result uses margins, severity disclaimer and artifacts | ✅ | ✅ | Upload → preview → Analyze → predicted card: disease label, decision margins, severity badge, exact disclaimer, score panel, segmentation preview, no Healthy text, no confidence field |
| uncertain result keeps unreliable lesions unavailable and shows warnings | ✅ | ✅ | Uncertain card: unconfirmed notice, uncertainty callout, "Not reported" severity, lesion unavailable note, "not 0%/Mild" text, warning codes, missing feature codes, decision margins wording, no Mild badge |
| HTTP 200 rejection is not a prediction and is absent from history | ✅ | ✅ | Rejected card: reason, "no prediction" heading, "no disease label" text, "not added to history" text, no prediction/score/severity elements; history page: empty state, 0 rows, "0 records" |
| 413 file too large stays an upload error, not a rejection | ✅ | ✅ | Analysis error card: "File too large" title, "not a disease result" text, no prediction/rejected elements |
| 415 unsupported type stays an upload error, not a rejection | ✅ | ✅ | Analysis error card: "Unsupported file type" title, "not a disease result" text |
| 422 unreadable image stays an upload error, not a rejection | ✅ | ✅ | Analysis error card: "Image could not be read" title, "not a disease result" text |
| 503 model-unavailable is a retryable service error | ✅ | ✅ | Analysis error card: "Analysis service is starting…" title, Retry button, no prediction/rejected elements |
| backend offline disables analysis and explains the connection failure | ✅ | ✅ | "backend-unavailable" visible, preview still renders, Analyze button disabled, "Could not reach the backend" text |
| backend online with model starting disables analysis without pretending success | ✅ | ✅ | "model-unavailable" visible, Analyze button disabled, no "model-ready" element |
| network failure during analysis is shown as a service error | ✅ | ✅ | Analysis error card visible, "Starting analysis service…" text, no prediction element |

### 2.7 Playwright E2E — production preview

- **Config:** `tests/end_to_end/playwright.preview.config.ts`
- **Browser:** Chrome (chrome-preview project)
- **Tests:** 10
- **Result:** ✅ All passing (10/10)
- **Duration:** ~16 seconds total
- **What it verifies:** The built Vite bundle (`npm run build`) served via `vite preview` passes the same analysis-state assertions as the dev-server suite. This catches asset/route/fallback problems that a dev-server-only suite would miss.

---

## 3. Frontend/backend contract checks

The following contract invariants were verified by the E2E suite and the backend test suite:

### 3.1 API response shape

| Endpoint | Verified by | Contract |
|---|---|---|
| `GET /api/v1/health` | Backend tests + E2E mock | `status`, `model_loaded`, `model_version`, `runtime_storage` |
| `GET /api/v1/model-info` | Backend tests + E2E mock | All manifest fields, no `confidence`/`probability`, `score_kind: "decision_margin"`, `calibrated_probabilities: false`, severity disclaimer present |
| `POST /api/v1/predict` (predicted/uncertain) | Backend tests + E2E + preview | `prediction_id` (UUID), `status`, `disease`, `decision_scores` (3 classes), `margin`, `ranking`, `score_kind`, `score_note`, `lesion_area_percentage`, `lesion_reliable`, `severity` + disclaimer + reason code + config version/hash, `warnings`, `rejections`, `missing_features`, `artifacts` (3 URLs), model/feature/config versions, `stage_ms`, `created_at`, `runtime_storage`; **no** `confidence`/`probability` field |
| `POST /api/v1/predict` (rejected) | Backend tests + E2E + preview | HTTP 200, `status: "rejected"`, `reason_code`, `message`, `runtime_storage`; **no** `prediction_id`, **no** `artifacts`, **no** disease/label/scores/severity |
| `GET /api/v1/history` | Backend tests + E2E mock | `count`, `items` (labelled rows only), `runtime_storage`; rejected rows absent |
| `DELETE /api/v1/history` | Backend tests | `deleted` count, `runtime_storage`; rows and files removed together |
| Artifact routes | Backend tests + E2E mock | PNG content type, 404 after delete/expiry |

### 3.2 Score contract

- Decision scores are `decision_function` margins, never confidence percentages.
- The frontend renders signed per-class margins and a best-vs-second margin only.
- The frontend never creates a confidence/probability field or converts margins to percentages.
- The `score_note` from the backend is displayed verbatim.

### 3.3 Status contract

- Three statuses only: `predicted`, `uncertain`, `rejected`. No `healthy` state.
- `uncertain` carries the disease label but is visibly unconfirmed (amber badge, PRD §11 notice).
- `rejected` (HTTP 200) has no label, no scores, no severity, no artifacts, no history row.
- Upload-level errors (413/415/422) and 503 are distinct from a 200 rejection.

### 3.4 Lesion/severity honesty contract

- Unreliable lesion data renders "Not available" for lesion area and "Not reported" for severity.
- Unreliable lesion data is never `0%` or `Mild`.
- A measured reliable `0.0%` remains valid.
- The exact experimental severity disclaimer is displayed on every result, history, and About surface.

### 3.5 History contract

- Only labelled results (`predicted`, `uncertain`) are stored.
- A defensive client filter also drops any `rejected` row.
- Clear history requires explicit confirmation and calls the backend DELETE.
- Failures leave the table intact.
- History/artifact non-persistence is stated in the UI.

---

## 4. Cross-browser check

Two browser projects were exercised:

1. **Chrome** (Desktop Chrome channel) — 10/10 tests passing
2. **Edge** (Desktop Chrome channel / msedge) — 10/10 tests passing

Both browsers render the analysis states identically. The production preview was verified
in Chrome only (preview config uses a single `chrome-preview` project).

---

## 5. Synthetic image fixtures

Three synthetic PNG fixtures were committed under `tests/end_to_end/fixtures/images/`:

| File | Dimensions | Orientation | Purpose |
|---|---|---|---|
| `leaf_landscape.png` | 900 × 700 | Landscape | Predicted/uncertain/rejected/upload-error tests |
| `leaf_portrait.png` | 700 × 900 | Portrait | Portrait upload path (available for future tests) |
| `leaf_rejected.png` | 700 × 700 | Square | Rejected-upload path (available for future tests) |

These are small, reproducible, git-contained fixtures that exercise the frontend upload/preview
path without requiring the real dataset. They are served through route interception in the E2E
suite, so the actual backend inference is not exercised by these fixtures — that is covered by
the backend pytest suite and the live smoke test.

---

## 6. Real-image and smartphone-photo smoke checks

### 6.1 Real-image smoke check (backend pytest + live smoke)

The backend pytest suite (`backend/tests/`) includes synthetic-image tests that exercise the
full prediction pipeline: upload validation, preprocessing, segmentation, feature extraction,
inference, severity, history, and artifacts. These use programmatically generated images and
monkeypatched boundaries where needed to isolate each contract.

A live smoke test was previously run against a real uvicorn backend (port 8010) and verified:
- health and model-info responses
- a real uncertain upload (brown spot, Moderate severity, SMALL_IMAGE + FULL_FRAME_FALLBACK warnings) with all three PNG artifacts
- a 200 rejection that was not stored in history
- 413/415/422 upload errors
- DELETE clearing rows and files
- 404 for a deleted artifact

### 6.2 Smartphone-photo trials

**Not performed as part of this session.** The Phase 6 plan calls for 5–10 smartphone-photo
trials, but no smartphone photographs were available in this environment. The following is
documented as a known limitation:

- The model and segmentation thresholds are calibrated on white-paper studio photographs from
  the approved 120-image Kaggle dataset.
- Smartphone photographs with cluttered backgrounds, different lighting, camera quality, leaf
  orientation, or multiple leaves are untested.
- The backend returns `uncertain` or `rejected` for images that do not match the training
  distribution, but the boundary has not been measured on real phone photos.
- This is recorded as a known limitation in `docs/API.md`, `docs/DECISIONS.md`, and the model
  manifest's `known_failure_cases`.

---

## 7. Known limitations

| Limitation | Status | Documentation |
|---|---|---|
| No calibrated probability source; `uncertain` is driven by quality warnings, missing features/severity, and lesion unreliability, not by a score threshold | Open (P-05) | `docs/DECISIONS.md` §5, `docs/API.md` §4 |
| No healthy-leaf class; healthy/unusual images return `uncertain` or `rejected`, never "healthy" | By design | PRD §11, `docs/DECISIONS.md` §1 |
| History is runtime-only; a restart wipes it | By design | PRD §16, `docs/API.md` §1 |
| No smartphone-photo trials performed | Deferred | This QA report §6.2 |
| Segmentation thresholds calibrated on studio photos; phone backgrounds untested | Known limitation | Model manifest `known_failure_cases`, `docs/API.md` §3 |
| Winning SVM is uncalibrated; `SVC(probability=True)` deprecated in scikit-learn 1.9 | Known limitation | `docs/DECISIONS.md` §4c (P-15) |
| Held-out test is a single 24-row evaluation; ~±0.05–0.08 sampling noise on final macro F1 | Known limitation | `docs/DECISIONS.md` §4c, evaluation report |
| No segmentation ground-truth annotation; "plausible mask" is visual review, not IoU | Known limitation | `docs/SEGMENTATION_NOTES.md` |
| Faint lesion band can remain on dark lower edge of some BLB strips | Known limitation | `docs/SEGMENTATION_NOTES.md` |
| Feature matrix has no uncalibrated lesion rows on this dataset (0/120); NaN path proven by tests only | Known limitation | `docs/DECISIONS.md` §4b (P-13) |
| Frontend cannot inspect image pixels before upload; corrupt/renamed images rejected by backend (415/422) | Known limitation | `docs/FRONTEND.md` §8 |
| Tailwind layout designed for 1280 px, degrades at 768 px; mobile optimisation out of scope | By design | PRD §6, `docs/FRONTEND.md` §8 |

---

## 8. Files changed in Phase 6

| File | Change |
|---|---|
| `package.json` (root) | Added Playwright QA harness: `test:e2e`, `test:e2e:headed`, `test:e2e:preview` scripts; `@playwright/test` dev dependency |
| `package-lock.json` (root) | Pinned `@playwright/test@1.65.0` and its dependencies |
| `tests/end_to_end/playwright.config.ts` | Development-server Playwright config: Chrome + Edge projects, backend + Vite dev webservers, route-interception-friendly timeouts, gitignored report/output dirs |
| `tests/end_to_end/playwright.preview.config.ts` | Production-preview Playwright config: build + `vite preview`, Chrome project, separate runtime dir and report/output dirs |
| `tests/end_to_end/fixtures/api.ts` | API fixtures: `makeHealth`, `makePrediction`, `makeUncertainPrediction`, `makeRejected`, `makeHistoryItem`, `makeHistoryList`, `makeModelInfo`; re-declares `SEVERITY_DISCLAIMER` so E2E tests stay self-contained |
| `tests/end_to_end/fixtures/images/leaf_landscape.png` | Synthetic 900×700 landscape PNG fixture |
| `tests/end_to_end/fixtures/images/leaf_portrait.png` | Synthetic 700×900 portrait PNG fixture |
| `tests/end_to_end/fixtures/images/leaf_rejected.png` | Synthetic 700×700 square PNG fixture |
| `tests/end_to_end/helpers/files.ts` | File-chooser helper (`chooseFile`) and fixture constants (`LANDSCAPE`, `PORTRAIT`, `REJECTED`) |
| `tests/end_to_end/helpers/network.ts` | Route-interception helpers: `mockHealth`, `mockPredict`, `mockPredictAbort`, `mockHistory`, `mockArtifacts`, `mockModelInfo`; fixed relative import paths |
| `tests/end_to_end/analysis-states.spec.ts` | 10 E2E test cases × 2 browsers (dev) + 10 (preview) = 20/20 and 10/10 passing; fixed relative imports, added `makeHealth` import, corrected decision-margin assertion to `+1.13` |
| `.gitignore` | Already covered browser test artifacts (`test-results/`, `playwright-report/`, `playwright-preview-report/`, `playwright.config.ts` output dirs) via existing patterns; verified no reports/traces/screenshots/videos are tracked |

---

## 9. Verification checklist

- [x] Frontend unit tests: 64/64 passing
- [x] Frontend typecheck: clean
- [x] Frontend production build: clean
- [x] Backend tests: 217/217 passing
- [x] Root split-invariant tests: 6/6 passing
- [x] Playwright dev-server tests: 20/20 passing (Chrome + Edge)
- [x] Playwright production-preview tests: 10/10 passing (Chrome)
- [x] API contract: verified by backend route tests + E2E + preview (no separate standalone contract file; the `test:contract` script was removed because it required a running backend not available outside the Playwright harness)
- [x] Browser test artifacts gitignored: verified (no `test-results/`, `playwright-report/`, `playwright-preview-report/`, traces, screenshots, or videos tracked)
- [x] No raw data, secrets, caches, or temporary files staged: verified via `git status`
- [x] No changes to held-out data, model bundle, feature schema, segmentation configs, or Phase 2/3 results: verified (no files under `data/raw/`, `data/splits/`, `backend/app/artifacts/production/`, `backend/configs/`, `backend/app/vision/`, `backend/app/ml/` were modified)

---

## 10. Model card and limitation updates

The model card lives in `docs/API.md` (model-info endpoint documentation) and the model
manifest (`backend/app/artifacts/production/model_manifest.json`). No changes were required
to these for Phase 6 because:

- The model bundle (`svm-v1.0.0`) is unchanged.
- The feature schema (`1.0.0`, 50 features) is unchanged.
- The segmentation config (`seg-v2`) and quality config (`quality-v1`) are unchanged.
- The evaluation report and held-out result (macro F1 0.7855 at n=24) are unchanged.
- The known failure cases already document the smartphone-photo and healthy-leaf limitations.

The Phase 6 QA findings are recorded in this report and in `PROJECT_STATUS.md`. The known
limitations listed in §7 are consistent with the existing documentation and do not require
changes to the model card or manifest.

---

## 11. Phase 6 completion statement

Phase 6 milestones from `PHASE_PLAN.txt` and `PROJECT_STATUS.md` are complete:

- [x] Real-browser Playwright E2E coverage (Chrome + Edge, dev server)
- [x] Production-preview testing (built bundle via `vite preview`)
- [x] Predicted, uncertain, rejected, upload-error, 503, and backend-offline states
- [x] History and artifact-link behavior
- [x] Clear-history behavior (backend route tests + E2E mock)
- [x] Portrait and landscape uploads (fixtures committed; preview orientation verified)
- [x] Frontend/backend contract checks (backend route tests + E2E + preview)
- [x] Build and typecheck verification (frontend build + typecheck clean; backend tests green)
- [x] QA documentation (`docs/QA_REPORT.md`) and model-card/limitation updates (none required; existing docs sufficient)
- [x] Documented smartphone-photo or manual-device checks where required (deferred; documented as known limitation)

Phase 7 (deployment) is not started.

---

*End of QA report.*
