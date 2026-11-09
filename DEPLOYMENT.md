# Deployment: Vercel (frontend) + Render (backend)

The dashboard is a static Vite build. The FastAPI service is a long-running
Python web service with a committed model bundle. The browser talks to the API
directly, so two values must agree:

| Where | Variable | Value |
|---|---|---|
| Vercel | `VITE_API_BASE_URL` | `https://<your-service>.onrender.com` (origin only) |
| Render | `CORS_ORIGINS` | `https://<your-app>.vercel.app` (exact origin) |

`VITE_API_BASE_URL` is baked into the JavaScript at **build time**. Changing it
requires a Vercel redeploy, not just a restart.

## Current deployment

| Service | URL |
|---|---|
| Dashboard (Vercel) | <https://dhanya-drishti.vercel.app/> |
| API (Render) | <https://dhanya-drishti.onrender.com> |
| API documentation | <https://dhanya-drishti.onrender.com/docs> |
| Health check | <https://dhanya-drishti.onrender.com/api/v1/health> |

Cross-wiring for this deployment:

```
Vercel   VITE_API_BASE_URL=https://dhanya-drishti.onrender.com
Render   CORS_ORIGINS=https://dhanya-drishti.vercel.app
```

The live health endpoint reports `model_loaded: true` with `svm-v1.0.0`. The API
verifies every artifact hash and byte size in `model_manifest.json` at startup,
so a bundle that does not match its manifest reports `model_loaded: false` and
answers model-dependent endpoints with 503 instead of serving predictions.

## 1. Deploy the backend on Render

Use the included [`render.yaml`](./render.yaml) blueprint, or create a Web
Service manually:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python 3.11 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/v1/health` |
| Plan | Free is supported (with sleep, see below) |

Environment variables:

```
ENVIRONMENT=production
CORS_ORIGINS=https://dhanya-drishti.vercel.app
HISTORY_EXPIRY_MINUTES=60
HISTORY_SWEEP_INTERVAL_SECONDS=60
MAX_UPLOAD_MB=10
```

`HISTORY_EXPIRY_MINUTES` is the age at which a record becomes invalid;
`HISTORY_SWEEP_INTERVAL_SECONDS` is how often the running process deletes expired
rows **and** their PNG files. A lifespan task does this on a timer, so records
leave within about a minute of the 60-minute TTL even if nobody opens the history
page. Expired artifacts answer 404 immediately, before the sweep runs.

Do not use `*` for `CORS_ORIGINS`: the app sends `allow_credentials=True`, and a
wildcard would be rejected by browsers. Add every real origin, comma-separated
(for example the production domain plus a Vercel preview domain).

The model artifacts under `backend/app/artifacts/production/` are committed, so
no dataset or retraining step is needed on Render. Storage is ephemeral: history
and PNG artifacts are temporary by design and disappear on restart, sleep,
redeploy or expiry.

## 2. Deploy the frontend on Vercel

1. Import the repository and set **Root Directory** to `frontend`.
2. Framework preset: Vite. Build command `npm run build`, output `dist`
   (already declared in [`frontend/vercel.json`](./frontend/vercel.json)).
3. Add the environment variable for Production (and Preview if used):

   ```
   VITE_API_BASE_URL=https://dhanya-drishti.onrender.com
   ```

   These are the values of the current deployment; replace them if you are
   standing up a separate one.

4. Deploy. `frontend/vercel.json` rewrites client-side routes such as
   `/history` and `/about` to `index.html`, so a refresh or deep link does not
   return a 404.
5. Copy the final Vercel origin (`https://dhanya-drishti.vercel.app` today) into
   Render's `CORS_ORIGINS` and restart the backend service.

## 3. Smoke test

```bash
curl https://dhanya-drishti.onrender.com/api/v1/health
curl https://dhanya-drishti.onrender.com/api/v1/model-info
```

Expected health response:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "svm-v1.0.0",
  "runtime_storage": "temporary"
}
```

Then open the Vercel URL, confirm the Analyze page says “Model ready”, and visit
**Prediction History** and **About Model**. Both pages must render their text,
not the Retry card.

## 4. Free-tier sleep and what the frontend does

Render free web services **spin down after 15 minutes without inbound traffic**
and take about a minute to spin back up. The frontend is built for that:

- **Who wakes it**: opening the dashboard is enough. The app-wide health poll
  sends `GET /api/v1/health` as soon as the page mounts, which is the inbound
  request that starts the spin-up. The History and About Model pages also fetch
  on mount. Choosing a local file does **not** contact the API — uploads are
  validated in the browser and only sent when the user presses Analyze.
- **Analyze is gated**: the button stays disabled until health reports
  `model_loaded: true`, so a cold start cannot fire a prediction into a starting
  service. The page shows “Backend online — model still starting” (or the offline
  notice) instead.
- **Health**: retries every 5 seconds while offline and re-checks immediately
  when the browser comes back online or the tab becomes visible.
- **Keep-alive**: while a dashboard tab is open, the same poll hits
  `/api/v1/health` once a minute with `cache: 'no-store'`, which keeps a free
  instance awake during a review session. With no tab open nothing pings, so the
  next visit pays the cold start.
- **Failed predictions are not resubmitted automatically**: a request that fails
  during a cold start shows a distinct “waking up” / “starting” message and a
  manual Retry, and never becomes a history record.
- **History and model card**: retry automatically with exponential backoff
  (4 s, 8 s, 16 s, 30 s … up to six attempts) and show “Retrying automatically”
  alongside the manual Retry button. No reload is needed.
- **Gateway responses**: 502/503/504 from a sleeping or restarting instance are
  shown as “Analysis service is waking up…”, not as a crash.
- **Offline**: a banner appears when the device loses connectivity.
- **Artifacts**: an expired or unavailable PNG shows an in-app fallback instead
  of a broken image; downloads report a recoverable error.
- **Misconfiguration**: a production build without `VITE_API_BASE_URL` (or one
  pointing at `localhost`) shows a specific setup message and disables retrying,
  because retrying cannot fix it.
- **Render failures elsewhere**: an app-wide error boundary replaces a white
  screen with a reload screen.

An external uptime pinger (for example a scheduled request to `/api/v1/health`
every 10 minutes) reduces cold starts, but it is optional. Do not rely on
Render's own health check to prevent free-tier sleep, and do not add an in-app
self-ping: the sleeping process cannot wake itself, so it only burns free-instance
hours without guaranteeing uptime.

## 5. Things that will not work on the free tier

- **Persistent history**: the filesystem and SQLite store are ephemeral. Treat
  history as session-only, exactly as the UI states.
- **Multiple workers**: history/artifacts use local files, so run a single
  Uvicorn worker (the start command above does).
- **Large uploads**: Render's proxy and the app's `MAX_UPLOAD_MB=10` both limit
  request size. Keep the default.
- **Instant first request**: cold starts are inherent to the free plan. The
  automatic retry is the mitigation; a paid instance or uptime pinger is the
  alternative.

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| “Analysis service is not configured” | `VITE_API_BASE_URL` missing at build time | Add it in Vercel, redeploy |
| “points at this visitor's own computer” | `localhost` used in the deployed build | Set the Render URL, redeploy |
| Network error, backend healthy | `CORS_ORIGINS` does not include the exact Vercel origin | Update Render env, restart |
| “Backend endpoint not found” | URL includes `/api/v1` or points at Vercel | Use the bare Render origin |
| 502/504 for ~1 minute | Render cold start | Wait; the page retries automatically |
| History empty after a while | Backend slept/restarted, or the 60-minute TTL elapsed | Expected; history is temporary |
| Artifact URL answers 404 | The record is past its 60-minute TTL, or history was cleared | Expected; rows and PNGs are deleted together |
| `model_loaded: false` on a fresh deploy | Bundle does not match `model_manifest.json` | Re-export the bundle, commit it, redeploy |
