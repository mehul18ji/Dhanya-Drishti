const guidance = [
  'Upload one clear rice leaf where possible.',
  'Keep the leaf well lit and evenly exposed.',
  'Avoid heavy blur, shadows, glare and extreme distance.',
  'Make sure the diseased region is visible in the frame.',
  'Do not upload healthy leaves.',
  'If several leaves are visible, only the most suitable detected leaf is analysed.',
]

const pipeline = [
  'Validate file and decode image',
  'Correct orientation · preserve aspect ratio',
  'Check image quality',
  'Segment leaf and primary candidate',
  'Segment disease regions',
  'Extract colour, texture, shape and lesion features',
  'Classify with the best classical model',
  'Estimate lesion area and severity',
]

export function AnalyzePage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-900">Analyze Leaf</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-600">
            Upload a single photograph of a diseased rice leaf to receive a classical-ML prediction,
            a lesion-area estimate and an experimental severity estimate.
          </p>
        </div>
        <span className="badge w-fit border-ink-200 bg-white text-ink-600">
          Phase 0 · foundation build
        </span>
      </div>

      <div
        role="note"
        className="flex gap-3 rounded-xl border border-warn-300 bg-warn-50 p-4 text-sm text-warn-700"
      >
        <span aria-hidden="true" className="mt-0.5 text-base leading-none">
          ⚠
        </span>
        <p>
          This prototype supports only three diseased rice-leaf categories: Bacterial Leaf Blight,
          Brown Spot, and Leaf Smut. Do not upload healthy leaves. Results are academic estimates and
          should not be used as professional agricultural advice.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <section className="card p-5 lg:col-span-3" aria-labelledby="upload-heading">
          <h2 id="upload-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Upload and preview
          </h2>

          <div className="mt-4 flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-ink-300 bg-ink-50/60 px-6 py-12 text-center">
            <span
              aria-hidden="true"
              className="flex h-12 w-12 items-center justify-center rounded-full bg-white ring-1 ring-inset ring-ink-200"
            >
              <svg viewBox="0 0 24 24" className="h-6 w-6 text-ink-400" fill="none" strokeWidth="1.6">
                <path
                  d="M12 16V5m0 0L8 9m4-4 4 4"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"
                  stroke="currentColor"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <div>
              <p className="text-sm font-medium text-ink-800">Drag and drop a rice-leaf image</p>
              <p className="mt-1 text-xs text-ink-500">
                JPG, JPEG, PNG or WEBP · up to 10 MB · one leaf recommended
              </p>
            </div>
            <button
              type="button"
              disabled
              className="mt-1 cursor-not-allowed rounded-lg bg-ink-200 px-4 py-2 text-sm font-medium text-ink-500"
              title="File selection is implemented in Phase 5"
            >
              Choose file
            </button>
            <p className="text-xs text-ink-400">
              Upload and analysis become available in Phase 5 (dashboard).
            </p>
          </div>

          <div className="mt-5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">
              Before you upload
            </h3>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {guidance.map((item) => (
                <li key={item} className="flex gap-2 text-sm text-ink-600">
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    className="mt-0.5 h-4 w-4 flex-none text-accent-600"
                    fill="none"
                    strokeWidth="2"
                  >
                    <path d="m5 13 4 4L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="card p-5 lg:col-span-2" aria-labelledby="result-heading">
          <h2 id="result-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Prediction result
          </h2>

          <div className="mt-8 flex flex-col items-center gap-2 text-center">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 items-center justify-center rounded-full bg-ink-100"
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5 text-ink-400" fill="none" strokeWidth="1.6">
                <path d="M4 19V5m0 14h16" stroke="currentColor" strokeLinecap="round" />
                <path d="M8 15l3-4 3 2 4-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <p className="text-sm font-medium text-ink-700">No analysis yet</p>
            <p className="max-w-xs text-xs text-ink-500">
              A prediction card, confidence score, lesion-area estimate and severity estimate will
              appear here after an image is analysed.
            </p>
          </div>

          <div className="mt-6 border-t border-ink-100 pt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">
              Processing pipeline
            </h3>
            <ol className="mt-2 space-y-1.5">
              {pipeline.map((stage, index) => (
                <li key={stage} className="flex items-start gap-2 text-xs text-ink-500">
                  <span
                    aria-hidden="true"
                    className="mt-px flex h-4 w-4 flex-none items-center justify-center rounded-full bg-ink-100 text-[10px] font-semibold text-ink-500"
                  >
                    {index + 1}
                  </span>
                  {stage}
                </li>
              ))}
            </ol>
          </div>
        </section>
      </div>

      <p className="text-xs text-ink-500">
        Severity is an experimental estimate based on the visible lesion area in this image. It is not
        a validated agronomic severity grade.
      </p>
    </div>
  )
}
