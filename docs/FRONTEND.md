# DhanyaDrishti — Frontend (Phase 5)

> Status: **Phase 5 complete (2026-11-08)**. The React dashboard consumes the frozen
> Phase 4 API in `docs/API.md`. It does not change the model, dataset, features,
> segmentation, splits or held-out results.

---

## 1. Stack and commands

- React 18 + Vite 6 + TypeScript + Tailwind CSS v3.
- Runtime dependencies remain `react`, `react-dom` and `react-router-dom` only.
- Dev-only test toolchain: Vitest, jsdom, Testing Library (`@testing-library/react`,
  `jest-dom`, `user-event`). `fetch` and `URL.createObjectURL` are mocked; no browser
  automation is part of Phase 5.

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run test       # 64 Vitest tests
npm run typecheck
npm run build      # tsc --noEmit + vite build
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000` (see `frontend/.env.example`).
If Windows resolves `localhost` to IPv6 while the backend binds IPv4, set the value to
`http://127.0.0.1:8000` and add that origin to the backend CORS list.

## 2. Routes and component map

| Route | Page | Main components |
|---|---|---|
| `/` | `pages/AnalyzePage.tsx` | `ImageUploader`, `ImagePreview`, `AnalysisProgress`, `PredictionResultCard`, `RejectedResultCard`, `AnalysisErrorCard` |
| `/history` | `pages/HistoryPage.tsx` | `HistoryTable`, `ConfirmDialog`, `ErrorNotice` |
| `/about` | `pages/AboutModelPage.tsx` | model metrics, score-reading notes, supported classes, workflow, severity, limitations |

`DashboardLayout` provides the dark `Header` (product identity, `Model: Classical ML`,
live health/model badge), `Navigation` (Analyze Leaf / Prediction History / About Model)
and the persistent `Footer` disclaimer.

Data layer:

- `services/api.ts` — typed client: health, model info, multipart predict, history
  list/delete, artifact URL prefixing, request timeouts and `ApiError`.
- `types/api.ts` — exact response mirrors; no `confidence`/`probability` field exists.
- `hooks/useHealth.ts` — cold-start-aware health polling (5 s while offline or while the
  model is starting, 30 s when ready).
- `hooks/useHistory.ts` — temporary history list/reload/clear.
- `hooks/useModelInfo.ts`, `hooks/useObjectUrl.ts`.
- `utils/errors.ts` — friendly 413/415/422/503/network/timeout messages.
- `utils/measurements.ts` — hard gates for lesion/severity display.
- `utils/diseases.ts` — slug-to-label mapping and the healthy-label guard.

## 3. State contract

| State | Trigger | UI |
|---|---|---|
| Health checking | initial `/health` call | neutral “Checking the analysis service…” |
| Backend offline | health network error/timeout | warning “Starting analysis service…”, retry, analysis disabled |
| Model starting | `/health` 200 with `model_loaded: false` | amber “Backend online — model still starting”, analysis disabled |
| Empty result | no file analysed yet | explanatory result placeholder, no diagnosis |
| Loading | `/predict` in flight | staged, explicitly approximate indicator |
| Predicted | HTTP 200 `status: "predicted"` | white card, teal **Predicted** badge, label + margins + severity + artifacts |
| Uncertain | HTTP 200 `status: "uncertain"` | amber card/badge, the exact PRD §11 safeguard text, label shown as **unconfirmed** |
| Rejected analysis | HTTP 200 `status: "rejected"` | grey card with **no** label/scores/severity/artifacts; reason + guidance; “not added to history” |
| Upload failure | 413 / 415 / 422 | red upload-error card, no prediction |
| Model unavailable | 503 | amber service card, retryable, no prediction |
| History loading | initial list call | spinner row / skeleton state |
| History empty | list succeeds with zero labelled rows | empty state and Analyze link |
| History error | list fails | readable error + retry (cold-start message when applicable) |
| Clear confirmation | “Clear history” | modal with explicit irreversible-action text |

A rejected 200 response is visually and semantically separate from an upload error and from
a prediction. It creates no history row (enforced by the backend and asserted in the live
smoke test).

## 4. Locked honesty rules

1. **No confidence or probability display.** Scores are rendered only as one-vs-rest
   `decision_function` values and a best-vs-second margin. The UI says they are not
   probabilities; tests assert that no confidence field or confidence percentage appears.
2. **No healthy class.** `utils/diseases.ts` maps only the three disease slugs and refuses
   to render a healthy value as a disease result. The caveat remains visible.
3. **Unreliable lesion data never becomes `0 %` or `Mild`.** A missing or unreliable
   lesion area renders “Not available”; severity renders “Not reported” with the backend
   reason code. A genuinely measured `0.0 %` on a reliable leaf stays honest.
4. **Every severity render carries the exact experimental disclaimer.** The response
   `severity_disclaimer` is used in the result card; `/model-info` supplies the same text
   on About; History shows it once above the table.
5. **Warnings, missing features and rejection reasons stay visible.** Result cards list
   each warning and missing feature; history row details expose the same warning text.
6. **Temporary only.** History, originals and masks expire with the backend session; the
   UI never implies permanence.
7. **No internal objects leak.** Components consume only documented JSON fields; artifact
   paths are prefixed with `API_BASE_URL` and opened with
   `target="_blank" rel="noopener noreferrer"`.

## 5. Error mapping (client)

| Condition | Title | Retryable |
|---|---|---|
| Network failure | Starting analysis service… | yes |
| Client timeout | Analysis service is slow to respond | yes |
| 413 `FILE_TOO_LARGE` | File too large | no |
| 415 `UNSUPPORTED_FILE_TYPE` | Unsupported file type | no |
| 422 `IMAGE_TOO_SMALL` | Image too small | no |
| 422 `INVALID_UPLOAD` | Image could not be read | no |
| 503 `MODEL_NOT_LOADED` | Analysis service is starting… | yes |
| History 404 | Prediction not found | no |
| Other 5xx | Analysis failed | yes |

Client-side upload pre-check (extension, MIME, non-empty, 10 MB default) gives immediate
feedback; the backend remains authoritative.

## 6. History and artifacts

- `GET /api/v1/history` is loaded on page entry; only labelled rows are displayed, and a
  defensive client filter also drops any `rejected` row.
- The table shows thumbnail, timestamp/expiry, disease/status, severity, lesion area,
  best-vs-second margin and links to the three temporary PNGs.
- `DELETE /api/v1/history` is only sent after the confirmation dialog; rows **and**
  artifact files are removed by the backend. Errors leave the current table intact.
- Expired artifacts render an inline “Artifact unavailable (it may have expired)” state;
  links are never hidden behind a fake success.

## 7. Tests

`npm test` runs 13 files / 64 tests:

- API client: base URL, multipart field, typed 413/415/422/503, network, timeout,
  invalid body, artifact URL construction, history limit/delete.
- Upload: valid types, extension/MIME rejection, empty and oversize files, accessible
  button, disabled state.
- Preview: portrait, landscape, `object-contain`, metadata, remove action.
- Result cards: predicted, uncertain with exact PRD text, warnings, missing features,
  artifact links, severity disclaimer, no-confidence assertion, no `0 %`/`Mild` for an
  unreliable lesion, healthy-label guard.
- Rejected card: reason/guidance and absence of prediction fields.
- History: loading, empty, success, rejected-row filtering, warning details, artifact
  links, clear confirmation, clear failure, backend-waking retry, 404 clear mapping.
- Analyze flow: model-ready gating, upload → preview → prediction, loading, uncertain,
  200 rejection, 413, 503, backend off/retry, model-starting state.
- Header: online + model version, model-starting distinction, offline.
- About: metrics/provenance/classes/disclaimer, loading, 503 error.
- Error mapping unit tests for every distinct upload/service failure.

`npm run build` and `npm run typecheck` are clean; a production `vite preview` served `/`,
`/history`, `/about` and the hashed JS asset with HTTP 200. Backend `python -m pytest` remains
217 passed; the root split-invariant suite remains 6 passed.

Full browser-console automation is not part of Phase 5. The preview check confirms routing and
asset availability, but Phase 6 owns a real-browser E2E suite that can assert console errors.

## 8. Known limitations

- No real-browser E2E suite and no smartphone-photo trials yet — those are Phase 6 work.
- `uncertain` is still driven by quality warnings, missing features/severity and lesion
  unreliability; no calibrated score threshold exists (decision P-05 remains open).
- History is session-only; a restart wipes it. This is intentional.
- The frontend cannot verify image decodability before upload; the backend returns 422 for
  corrupt bytes and the UI maps it.
- Tailwind layout is designed for 1280 px and degrades at 768 px; mobile optimisation is
  out of scope for Version 1.
