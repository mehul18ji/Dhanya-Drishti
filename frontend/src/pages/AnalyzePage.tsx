import { useEffect, useRef, useState } from 'react'

import { AnalysisErrorCard } from '../components/analysis/AnalysisErrorCard'
import { AnalysisProgress } from '../components/analysis/AnalysisProgress'
import { PredictionResultCard } from '../components/analysis/PredictionResultCard'
import { RejectedResultCard } from '../components/analysis/RejectedResultCard'
import { Callout } from '../components/common/Callout'
import { ErrorNotice } from '../components/common/ErrorNotice'
import { PageHeader } from '../components/common/PageHeader'
import { Spinner } from '../components/common/Spinner'
import { ImagePreview } from '../components/upload/ImagePreview'
import { ImageUploader } from '../components/upload/ImageUploader'
import { useBackendHealth } from '../hooks/useBackendHealth'
import { API_BASE_URL, predict } from '../services/api'
import type { PredictResponse } from '../types/api'
import { apiTargetLabel, resolveApiTarget } from '../utils/apiTarget'
import { describeApiError, isAbortError } from '../utils/errors'
import type { FriendlyError } from '../utils/errors'

const GUIDANCE = [
  'Upload one clear rice leaf where possible.',
  'Keep the leaf well lit and evenly exposed.',
  'Avoid heavy blur, shadows, glare and extreme distance.',
  'Make sure the diseased region is visible in the frame.',
  'Do not upload healthy leaves.',
  'Phone-camera photographs are untested; use a clean, plain background where possible.',
  'If several leaves are visible, only the most suitable detected leaf is analysed.',
]

function EmptyResultState() {
  return (
    <section className="card flex min-h-[280px] flex-col justify-center p-6" data-testid="empty-result">
      <h2 className="text-lg font-semibold text-ink-900">Prediction result</h2>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-600">
        Select one rice-leaf photograph and choose <strong>Analyze leaf</strong>. The result will
        show a supported disease label, per-class decision margins, the measured lesion area, an
        experimental severity estimate, and any quality warnings.
      </p>
      <ul className="mt-4 space-y-2 text-sm text-ink-600">
        <li className="flex gap-2">
          <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 rounded-full bg-ink-300" />
          The result is one of three supported diseases, never “healthy”.
        </li>
        <li className="flex gap-2">
          <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 rounded-full bg-ink-300" />
          Unreliable lesion measurements are left unavailable, not reported as 0% or Mild.
        </li>
        <li className="flex gap-2">
          <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 rounded-full bg-ink-300" />
          Scores are model margins, not confidence percentages.
        </li>
      </ul>
    </section>
  )
}

export function AnalyzePage() {
  const health = useBackendHealth()
  const apiLabel = apiTargetLabel(resolveApiTarget(API_BASE_URL))
  const modelReady = health.state === 'online' && health.modelLoaded
  const unavailable = health.state === 'offline' || (health.state === 'online' && !health.modelLoaded)
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<PredictResponse | null>(null)
  const [error, setError] = useState<FriendlyError | null>(null)
  const [pending, setPending] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(
    () => () => {
      controllerRef.current?.abort()
    },
    [],
  )

  useEffect(() => {
    if (!pending && (result || error) && resultRef.current?.scrollIntoView) {
      resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [pending, result, error])

  const chooseFile = (selected: File) => {
    if (unavailable) return
    controllerRef.current?.abort()
    setPending(false)
    setFile(selected)
    setResult(null)
    setError(null)
  }

  const reset = () => {
    controllerRef.current?.abort()
    setPending(false)
    setFile(null)
    setResult(null)
    setError(null)
  }

  const analyze = async () => {
    if (!file || pending || !modelReady) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setPending(true)
    setResult(null)
    setError(null)

    try {
      const response = await predict(file, controller.signal)
      if (!controller.signal.aborted) setResult(response)
    } catch (caught) {
      if (!isAbortError(caught)) setError(describeApiError(caught, 'predict'))
    } finally {
      if (controllerRef.current === controller) setPending(false)
    }
  }

  const analyzeDisabled = !file || pending || !modelReady

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="DhanyaDrishti · Diagnostic workspace"
        title="Rice-leaf analysis, with the evidence"
        description="Upload one rice-leaf photograph to receive a supported disease label, decision-function margins, an experimental lesion-area estimate, and the quality caveats behind the result."
      />

      <Callout tone="warning" title="Academic prototype — read the limits first" className="block">
        <p>
          Supported labels are Bacterial Leaf Blight, Brown Spot and Leaf Smut. There is{' '}
          <strong>no healthy class</strong>: never treat a result as a healthy-leaf diagnosis. The
          model has <strong>not been validated on smartphone or field-camera photographs</strong>;
          it was calibrated on white-paper studio images, so phone photos may be unreliable.
        </p>
        <p className="mt-2">
          Scores are decision-function margins, <strong>not probabilities or confidence
          percentages</strong>, and the severity estimate is experimental. Do not use any result as
          professional agricultural advice.
        </p>
      </Callout>

      {health.state === 'checking' ? (
        <Callout tone="neutral" title="Checking the analysis service…" className="items-center">
          <p className="flex items-center gap-2">
            <Spinner className="h-3.5 w-3.5 text-ink-500" />
            Contacting the backend health endpoint. This usually takes less than a second.
          </p>
        </Callout>
      ) : null}

      {health.state === 'offline' && health.error ? (
        <div data-testid="backend-unavailable">
          <ErrorNotice
            error={health.error}
            onRetry={health.refresh}
            retryLabel="Retry connection"
            autoRetrying
          />
        </div>
      ) : null}

      {health.state === 'online' && !health.modelLoaded ? (
        <div data-testid="model-unavailable">
          <Callout tone="warning" title="Backend online — model still starting">
            <p>
              The API is reachable but the production model bundle is not loaded yet. Uploading and
              analysis are paused until the model is ready; the page checks again automatically.
            </p>
            <button
              type="button"
              onClick={health.refresh}
              className="mt-2 rounded-lg border border-warn-300 bg-white px-3 py-1.5 text-xs font-semibold text-warn-900 hover:bg-warn-100"
            >
              Check again
            </button>
          </Callout>
        </div>
      ) : null}

      {modelReady ? (
        <p className="text-xs text-ink-500" data-testid="model-ready">
          Model ready
          {health.modelVersion ? ` · ${health.modelVersion}` : ''} ·          Connected to the {apiLabel} API · images are processed in temporary runtime storage only.
        </p>
      ) : null}

      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        <section className="card p-4 sm:p-5" aria-labelledby="upload-heading">
          <div className="flex items-baseline justify-between gap-2">
            <h2 id="upload-heading" className="text-lg font-semibold text-ink-900">
              1. Select an image
            </h2>
            <span className="text-xs text-ink-500">JPG · JPEG · PNG · WEBP</span>
          </div>

          <div className="mt-3 rounded-lg border border-ink-200 bg-ink-50/70 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
              Before you upload
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-ink-600">
              {GUIDANCE.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="mt-4">
            <ImageUploader
              file={file}
              onFileSelected={chooseFile}
              disabled={pending || unavailable}
            />
          </div>

          {file ? (
            <div className="mt-4">
              <ImagePreview file={file} onRemove={reset} disabled={pending} />
            </div>
          ) : null}

          <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
            <button
              type="button"
              onClick={() => void analyze()}
              disabled={analyzeDisabled}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-accent-700 disabled:cursor-not-allowed disabled:bg-ink-300 sm:w-auto"
            >
              {pending ? <Spinner className="h-4 w-4 text-white" /> : null}
              {pending ? 'Analysing…' : 'Analyze leaf'}
            </button>
            {file ? (
              <button
                type="button"
                onClick={reset}
                disabled={pending}
                className="w-full rounded-lg border border-ink-300 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                Clear
              </button>
            ) : null}
          </div>

          {unavailable ? (
            <p className="mt-2 text-xs text-warn-800">
              {file
                ? 'Analysis is disabled until the backend and model are ready. The retry button above refreshes the health status.'
                : 'Uploads are paused while the analysis service is unavailable. The rest of the dashboard stays usable; uploads resume automatically when the backend reconnects.'}
            </p>
          ) : !file ? (
            <p className="mt-2 text-xs text-ink-500">
              Choose a file to enable analysis.
            </p>
          ) : null}
        </section>

        <div ref={resultRef} className="min-w-0 scroll-mt-4" aria-live="polite">
          {pending ? <AnalysisProgress fileName={file?.name} /> : null}
          {!pending && error ? (
            <AnalysisErrorCard
              error={error}
              onRetry={() => void analyze()}
              retrying={pending}
            />
          ) : null}
          {!pending && !error && result?.status === 'rejected' ? (
            <RejectedResultCard rejection={result} onChooseAnother={reset} />
          ) : null}
          {!pending && !error && result && result.status !== 'rejected' ? (
            <PredictionResultCard prediction={result} onAnalyzeAnother={reset} />
          ) : null}
          {!pending && !error && !result ? <EmptyResultState /> : null}
        </div>
      </div>
    </div>
  )
}
