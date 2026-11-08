import { useEffect, useState } from 'react'

import { Spinner } from '../common/Spinner'

const STAGES = [
  'Uploading image',
  'Validating upload',
  'Segmenting leaf',
  'Extracting colour, texture, shape and lesion features',
  'Classifying with the production SVM',
  'Estimating experimental severity',
] as const

/**
 * Indeterminate progress with approximate stage labels.
 *
 * The backend returns one JSON response rather than streaming stage events, so the
 * dashboard never claims exact progress. The caption says so explicitly.
 */
export function AnalysisProgress({ fileName }: { fileName?: string }) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    setIndex(0)
    const timer = window.setInterval(() => {
      setIndex((current) => Math.min(current + 1, STAGES.length - 1))
    }, 1_400)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <section
      className="card p-5"
      aria-labelledby="analysis-progress-heading"
      data-testid="analysis-progress"
    >
      <div className="flex items-center gap-3">
        <Spinner className="h-5 w-5 text-accent-600" />
        <div>
          <h2 id="analysis-progress-heading" className="text-sm font-semibold text-ink-900">
            Analysing image
          </h2>
          <p className="text-xs text-ink-500">
            {fileName ? fileName : 'Running the classical vision pipeline on the backend.'}
          </p>
        </div>
      </div>

      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-ink-100">
        <div className="h-full w-2/5 animate-pulse rounded-full bg-accent-500" />
      </div>

      <ol className="mt-4 space-y-2 text-sm" aria-live="polite">
        {STAGES.map((stage, stageIndex) => {
          const current = stageIndex === index
          return (
            <li
              key={stage}
              className={[
                'flex items-center gap-2',
                current ? 'font-semibold text-ink-900' : 'text-ink-500',
              ].join(' ')}
            >
              <span
                className={[
                  'inline-block h-2 w-2 rounded-full',
                  current ? 'bg-accent-500' : 'bg-ink-200',
                ].join(' ')}
              />
              {stage}
              {current ? <span className="text-xs font-normal text-ink-500">in progress</span> : null}
            </li>
          )
        })}
      </ol>

      <p className="mt-4 rounded-md bg-ink-50 px-3 py-2 text-xs text-ink-500">
        Stage labels are approximate: the backend runs the whole pipeline in one request and does
        not stream progress. CPU inference usually takes a few seconds.
      </p>
    </section>
  )
}
