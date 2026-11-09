# DhanyaDrishti — Localhost Acceptance Report

> **Run date:** 2026-11-09
> **Scope:** local acceptance correction only. No cloud deployment was started.
> **Environment:** Windows 11, Python 3.11.9, Node v25.9.0, npm 11.12.1,
> Chrome + Edge (Playwright 1.65.0), CPU-only.
> **Model bundle:** `svm-v1.0.0` (unchanged). **Feature set:** `1.0.0` (unchanged).
> **Configs:** `seg-v2`, `quality-v1`, `severity-v1` (unchanged).
> **Dataset / splits / held-out rows:** unchanged. No retraining, no re-calibration,
> no metric change, no production-bundle change.

This report supersedes the restart-cleanup finding in the previous full-stack
acceptance run. Everything else was re-checked end to end on localhost.

---

## 1. The one real failure: restart did not appear to clear history

### 1.1 Reproduction (real application, same `RUNTIME_DIR`)

Reproduced with two **real** `uvicorn app.main:app` processes, an explicit absolute
`RUNTIME_DIR`, and a real prediction from a real dataset image:

| Step | Observed |
|---|---|
| First process started, health reports `model_loaded: true` | `svm-v1.0.0` |
| Real prediction created | id `e985dd64-…`, 3 PNG artifacts, 1 history row |
| Process stopped completely | exit code 1 (hard terminate), port released |
| State left on disk after stop | `history.sqlite3` present, 1 artifact dir, 3 PNG files |
| **Fresh** process, **same** `RUNTIME_DIR` | history `0`, artifact dirs `[]`, files `0`, old artifact URLs `404` |

### 1.2 Cause

**The application is not at fault.** `app.main:lifespan` calls
`HistoryService.start_fresh()`, which deletes the SQLite file (plus WAL/SHM) and every
artifact directory before serving anything. That works after a hard kill, which is
exactly the state a killed process leaves.

The previous acceptance failure came from the **restart harness**:

1. `tests/end_to_end/playwright.config.ts` and `playwright.preview.config.ts` set the
   backend `reuseExistingServer: !process.env.CI` — `true` locally. If a backend was
   already listening on `127.0.0.1:8000`, Playwright silently reused it, so the
   `RUNTIME_DIR` configured for the new run was never applied and **no lifespan ever
   ran**.
2. A harness that stops a wrapper/shell process (or only waits for the port to answer
   again) can also read the still-running old server. The "restart" then observes the
   old process's history.
3. Windows hard termination skips graceful shutdown (`history.close()` never runs,
   exit code 1), which is expected and documented: PRD §16 makes **startup** cleanup
   the guarantee ("clear all temporary storage at backend startup"), with graceful
   shutdown only "where possible".

So the failure was **incorrectly reused server process / flawed restart harness**, not
startup or shutdown cleanup, and not an inconsistent `RUNTIME_DIR`.

### 1.3 Fix (requirement not weakened)

| Change | Effect |
|---|---|
| `tests/end_to_end/playwright.config.ts`, `playwright.preview.config.ts`: backend `reuseExistingServer: false` | Every suite owns its backend process, so its `RUNTIME_DIR` and startup wipe always apply. A stale listener now fails the run instead of silently serving old state. |
| `scripts/check_restart_cleanup.py` (new) | Two real uvicorn processes, same `RUNTIME_DIR`, one real prediction. It proves the first PID exited **and** the port is closed before the second start, so a reused process cannot fake a pass. |
| `backend/tests/test_restart_cleanup.py` (new, 3 tests) | Pins startup cleanup in the app itself: leftover row + 3 artifact files (no graceful `close()`), then a fresh lifespan must show `0` rows, `404` for the old id/artifact, and no files. Also covers a second lifespan over the same directory and a left-behind DB without files. |

### 1.4 Restart-cleanup evidence (this acceptance run)

```
[PASS] backend restart clears temporary history and artifacts
       fresh pid=8140 | same RUNTIME_DIR
       history 8 -> 0
       artifact files 24 -> 0
       old URLs {'original_url': 404, 'leaf_mask_url': 404, 'lesion_mask_url': 404}
[PASS] restarted process can predict
[PASS] clear history removes rows, files and artifact URLs
       deleted=1 | history 1 -> 0 | artifact files left=0 | urls all 404
```

Dedicated harness (`python scripts/check_restart_cleanup.py`):

```
PASS: a fresh process with the same RUNTIME_DIR cleared history and artifacts
      (prediction 791dbc18-04b4-41bb-9545-191196715f8d)
first stop: exit code 1, port closed
leftover after stop: sqlite present, 1 artifact dir, 3 files
second start: history 0, artifact dirs 0, artifact files 0, old URLs 404
```

---

## 2. Pass / fail / untested

Legend: **PASS** = verified in this run; **UNTESTED** = cannot be verified with the
available hardware/data; nothing was fabricated.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Real dataset smoke prediction | **PASS** | `Brown spot/DSC_0105.jpg` → `predicted` brown_spot, margin 1.3652, lesion 28.26 %, Severe |
| 2 | Held-out smoke prediction | **PASS** | `Bacterial leaf blight/DSC_0367.JPG` → `predicted` bacterial_leaf_blight, margin 1.3778, lesion 8.92 %, Mild, 3 artifacts |
| 3 | Landscape upload | **PASS** | 3081×897 → same result as #2 |
| 4 | Portrait upload (rotated real pixels) | **PASS** | 897×3081 → `predicted` bacterial_leaf_blight, lesion 3.59 %, Mild |
| 5 | EXIF orientation 6 upload | **PASS** | EXIF-tagged landscape decoded to 466×1600 portrait → `predicted` bacterial_leaf_blight, lesion 8.66 %, Mild |
| 6 | Multiple leaves | **PASS** (safe handling) | 200 `uncertain`, leaf_smut, lesion 17.17 %, `FULL_FRAME_FALLBACK`; no crash. `MULTIPLE_LEAVES` warning was **not** emitted (see §8) |
| 7 | Poor-quality image | **PASS** | Dark/blurred real leaf → 200 `rejected`, `VERY_DARK_IMAGE`, no prediction row |
| 8 | Healthy-looking image | **PASS** (honest handling) | 200 `uncertain`, leaf_smut, 0.0 % lesion → Mild, `BLURRY_IMAGE`; never "healthy" (see §8) |
| 9 | Non-rice image (wheat) | **PASS** (honest handling) | 200 `uncertain`, leaf_smut, lesion 55.30 %, Severe, `FULL_FRAME_FALLBACK`; never "healthy" (see §8) |
| 10 | Rejected valid image | **PASS** | Blank readable PNG → HTTP 200 `rejected`, `NO_CLEAR_LEAF_FOUND`, no prediction id, no artifacts, history unchanged 8 → 8 |
| 11 | Invalid upload — oversize | **PASS** | 11 MB `.jpg` → HTTP 413 `FILE_TOO_LARGE` |
| 12 | Invalid upload — wrong type | **PASS** | `notes.txt` → HTTP 415 `UNSUPPORTED_FILE_TYPE` |
| 13 | Invalid upload — corrupt bytes | **PASS** | `broken.png` → HTTP 422 `INVALID_UPLOAD` |
| 14 | History retrieval | **PASS** | `count=8`, ids exactly the 8 labelled predictions, single row 200 |
| 15 | Artifact retrieval | **PASS** | `original`, `leaf_mask`, `lesion_mask` all 200 `image/png` |
| 16 | Clear history | **PASS** | `deleted=1`, rows 1 → 0, files 0, artifact URLs 404 |
| 17 | Backend restart cleanup | **PASS** | §1.4: history 8 → 0, 24 → 0 files, fresh PID, same `RUNTIME_DIR` |
| 18 | Browser upload → real API → real pipeline → real model | **PASS** | Playwright Chrome + Edge, dev server: predicted BLB, margin 1.3778, 3 artifact PNGs loaded, 295 ms round trip |
| 19 | Production-bundle browser path | **PASS** | `vite preview` + real backend: 11/11 tests, 3 artifacts, 0 console/network errors |
| 20 | Browser console / network | **PASS** | 0 console errors, 0 page errors, 0 failed requests, 0 5xx. One ignored console 404 (`/favicon.ico`) and 3 deliberate `ERR_ABORTED` cancellations, both documented in §8 |
| 21 | Response-time measurement | **PASS** | cold 1660.9 ms; warm n=7 mean 227.5 ms, p50 229.5 ms, p95 259.3 ms |
| 22 | Preprocessing resize/crop/letterbox | **PASS** | §5: uniform scale, no stretch, symmetric letterbox to 512×512 |
| 23 | Smartphone testing | **UNTESTED** | Not tested because no real smartphone rice-leaf image was available. |
| 24 | Cloud deployment | **NOT STARTED** | Explicitly out of scope for this session |

---

## 3. Held-out smoke test (functional only)

The fixed held-out manifest (`data/splits/test.json`) was read; no new image was
requested. The first manifest item was used **in place** (read only, never copied or
committed):

```
data/raw/rice_leaf_diseases/Bacterial leaf blight/DSC_0367.JPG
```

Manifest label: `bacterial_leaf_blight` (8/8/8 held-out protocol unchanged).

| Field | Result |
|---|---|
| HTTP | 200 |
| Status | `predicted` |
| Disease | `bacterial_leaf_blight` (matches the manifest label) |
| Decision scores (margins, **not** confidence) | BLB `+2.2241`, Brown Spot `+0.8463`, Leaf Smut `−0.1815` |
| Best-vs-second margin | `+1.3778` |
| Lesion area | 8.92 % (reliable) |
| Severity (experimental) | Mild |
| Warnings | none |
| Artifacts | 3 PNGs, all HTTP 200 |

The same image was uploaded through the real browser on Chrome and Edge and returned
the identical scores and artifacts. **This result was not used for tuning and no
held-out metric was recomputed or changed.** The held-out split, model, feature schema,
segmentation configuration and production bundle are untouched.

---

## 4. Rejected / invalid / uncertain — distinction kept

| Case | HTTP | Prediction id | History | Artifacts | Label |
|---|---|---:|---|---|---|
| Valid readable image, no clear leaf | 200 | **no** | **no row** | **none** | none |
| Oversize upload | 413 | — | — | — | — |
| Unsupported type | 415 | — | — | — | — |
| Corrupt/unreadable bytes | 422 | — | — | — | — |
| Poor-quality but readable image | 200 | no | no row | none | none (`VERY_DARK_IMAGE`) |
| Low-uncertainty / out-of-distribution | 200 | yes | yes | yes | label kept but status `uncertain` |

- A **rejected** result is HTTP 200 with a `reason_code` and a message, and no
  `prediction_id`, no artifacts and no history row.
- **Invalid uploads** stay typed HTTP errors (413/415/422) and are never styled as a
  rejection or a prediction.
- An **uncertain** labelled result keeps its label but is visibly unconfirmed; it is
  stored with its warnings so history stays honest.
- **No Healthy result exists.** The word "Healthy" never appears as a status/label in
  any response or UI state; the frontend assertion checks this on every browser run.
- Decision scores are never called confidence: responses use `decision_margin` and the
  UI renders signed margins only (`confidence`/`probability` fields do not exist).

---

## 5. Preprocessing resize / crop / letterbox evidence

Measured by running the real Phase 2 pipeline (`run_segmentation`) on the same bytes:

| Input | Source | Working (long side 768) | Leaf crop | Resize | Pad | Canvas | Uniform scale (max deviation) |
|---|---|---|---|---|---|---|---|
| Held-out landscape | 3081×897 (aspect 3.4348) | 768×224 | 768×207 (3.7101) | 512×138 (3.7101) | left 0, top 187 | 512×512 | yes (0.181 %) |
| Rotated portrait | 897×3081 (0.2911) | 224×768 | 207×768 (0.2695) | 138×512 (0.2695) | left 187, top 0 | 512×512 | yes (0.181 %) |
| EXIF orientation 6 | 466×1600 (0.2913) | 224×768 | 207×768 (0.2695) | 138×512 (0.2695) | left 187, top 0 | 512×512 | yes (0.143 %) |

- The crop aspect equals the resized aspect exactly; padding is symmetric.
- X and Y scale factors differ only by integer-pixel rounding (max 0.181 %), which is
  not stretching. No blind centre crop happens before leaf detection; the leaf bounding
  box is cropped first and then letterboxed.
- A vision/feature/segmentation change was **not** made; this is measurement only.

---

## 6. Timing results (CPU, Windows 11)

| Metric | Value |
|---|---:|
| First labelled request (cold: bundle already loaded, first pipeline run) | 1660.9 ms |
| Warm labelled requests (n = 7) mean | 227.5 ms |
| Warm p50 | 229.5 ms |
| Warm p95 | 259.3 ms |
| Warm pipeline-stage total mean (excludes HTTP/UI) | 137.2 ms |
| Browser round trip, dev suite (Chrome, real upload → HTTP response) | 295 ms |
| Browser round trip, production preview (first request) | 1860 ms |

The cold sample includes first-use OpenCV/NumPy/scikit-learn warm-up; warm p95 stays
under 0.3 s. These are local machine numbers, not a deployment SLA.

---

## 7. Test suites run

| Suite | Command | Result |
|---|---|---|
| Backend pytest | `cd backend && python -m pytest -q` | **222 passed** (217 + 3 restart tests + 2 acceptance-reporting tests) |
| Root split invariants | `python -m pytest tests -q` | **6 passed** |
| Frontend unit/component | `cd frontend && npm test` | **64 passed** (13 files) |
| Frontend typecheck | `npm run typecheck` | **clean** |
| Frontend build | `npm run build` | **clean** |
| Playwright dev (all specs, Chrome + Edge) | `cd tests/end_to_end && npx playwright test` | **22 passed** (11 × 2) |
| Playwright production preview (Chrome) | `npx playwright test --config=playwright.preview.config.ts` | **11 passed** |
| Local acceptance matrix | `python scripts/run_local_acceptance.py --evidence <external-temp-path>` | **38 / 38 checks passed**; external evidence path reported without error |
| Real-process restart check | `python scripts/check_restart_cleanup.py` | **PASS** |

Total automated test cases: **222 + 6 + 64 + 22 + 11 = 325**, plus 38 acceptance checks
and the standalone restart harness.

---

## 8. Known limitations (observed in this run)

| Limitation | Observation / status |
|---|---|
| Healthy-looking leaf | Returned `uncertain` leaf_smut with `BLURRY_IMAGE`, and a measured 0.0 % lesion was bucketed **Mild** by the locked provisional thresholds. It is unconfirmed and never called healthy, but the label/severity are not meaningful. This is the known no-healthy-class limitation, not a regression. |
| Non-rice (wheat) image | Returned `uncertain` leaf_smut, 55.3 % lesion, Severe. The pipeline has no out-of-distribution class; `uncertain` is the honest state but the numbers are meaningless. |
| Multiple-leaf photo | Handled safely as `uncertain` with `FULL_FRAME_FALLBACK`; the dedicated `MULTIPLE_LEAVES` warning did not appear because the mask fell back to the full frame. |
| Poor-quality image | Rejected with `VERY_DARK_IMAGE` on the synthetic dark/blurred variant. The exact rejection boundary for real phone photos is unmeasured. |
| Smartphone photography | **Not tested because no real smartphone rice-leaf image was available.** No smartphone result is claimed anywhere in this report. |
| Vite dev `/favicon.ico` | Browser requests the default favicon; the dev server answers 404, producing one cosmetic console error. Excluded from the console assertion and recorded here; no application request failed. |
| Deliberate request cancellations | `useHealth`/history abort in-flight fetches on unmount/refresh; Playwright reports these as `net::ERR_ABORTED`. Excluded as intentional; real network failures remain fatal. |
| No calibrated probabilities | Decision scores remain `decision_function` margins; `uncertain` is not driven by a calibrated score threshold (P-05 open). |
| History is runtime-only | Verified: restart wipes it. Nothing survives restart, redeploy, sleep or expiry. |
| Held-out sample size | One 24-image evaluation; ±0.05–0.08 sampling noise remains on macro F1. The smoke run is functional only. |
| Hard-kill shutdown cleanup | Hard termination skips graceful shutdown (observed exit code 1). Startup wipe is the guarantee and was verified with leftovers present. |
| Segmentation labels | No IoU ground truth; "plausible mask" remains visual review. |

---

## 9. What changed for this acceptance run

| File | Change |
|---|---|
| `tests/end_to_end/playwright.config.ts` | Backend `reuseExistingServer: false` so a suite always owns its backend process and `RUNTIME_DIR` |
| `tests/end_to_end/playwright.preview.config.ts` | Same backend change |
| `backend/tests/test_restart_cleanup.py` | New regression tests (3) for startup/restart cleanup with the same runtime directory |
| `scripts/check_restart_cleanup.py` | New real-process restart harness with explicit PID/port death checks |
| `scripts/run_local_acceptance.py` | Full localhost acceptance matrix + evidence writer; final reporting now accepts an evidence path outside the repository without raising `ValueError` |
| `backend/tests/test_local_acceptance_reporting.py` | New focused regression tests (2) for repository-relative and external evidence paths |
| `tests/end_to_end/local-acceptance.spec.ts` | New no-mock browser acceptance test (real upload, console/network, history, clear) |
| `docs/local_acceptance/api_evidence.json` | Machine-readable evidence from the 38-check run |
| `data/local_acceptance_inputs/` | Local-only acceptance photographs (healthy-looking, multiple-leaf, non-rice wheat). Untracked and gitignored; kept on disk. The matrix requires them, exactly like the gitignored raw dataset. |
| `docs/LOCAL_ACCEPTANCE_REPORT.md` | This report |
| `.gitignore` | Ignores `backend/.runtime-*/` directories used by the harnesses |
| `PROJECT_STATUS.md`, `docs/QA_REPORT.md`, `README.md`, `docs/AGENT_HANDOFF.md` | Status and QA documentation updates |

No model, dataset, split, held-out row, feature schema, segmentation config, severity
config or production artifact was modified, and no Git history command was run.

---

## 10. Conclusion

The previously reported restart failure was a harness defect (a reused live server),
not an application defect. The harness now proves process death and port release, the
Playwright suites can no longer silently reuse a backend, and startup cleanup is pinned
by a regression test. The final evidence-path bug was also a harness/reporting defect:
all 38 checks passed but the final `relative_to(REPO_ROOT)` print raised when `--evidence`
pointed outside the repository; it now reports the absolute path safely, with a focused
regression test. All 38 local acceptance checks pass, including a fresh-process restart
with the same `RUNTIME_DIR` (8 history rows → 0, 24 artifact files → 0, old URLs 404).
Smartphone testing remains **untested** because no real smartphone rice-leaf image was
available, and deployment was not started.
