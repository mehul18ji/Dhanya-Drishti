import { Callout } from '../components/common/Callout'
import { ErrorNotice } from '../components/common/ErrorNotice'
import { AlertTriangleIcon, LeafIcon, ShieldIcon } from '../components/common/Icons'
import { Metric, MetricGrid } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import { Spinner } from '../components/common/Spinner'
import { useModelInfo } from '../hooks/useModelInfo'
import { GENERAL_DISCLAIMER, HEALTHY_CAVEAT, DATASET_SOURCE_NAME, DATASET_SOURCE_URL, SMARTPHONE_CAVEAT } from '../utils/disclaimers'
import { SUPPORTED_DISEASES } from '../utils/diseases'
import { formatDecimal } from '../utils/format'

const WORKFLOW = [
  'Image input and upload validation',
  'Preprocessing with EXIF orientation correction',
  'Resizing without distortion (uniform scale) and letterbox padding',
  'Noise removal',
  'RGB → HSV and Lab conversion',
  'Leaf segmentation and primary-leaf selection',
  'Disease-region segmentation inside the leaf mask',
  'Colour, texture, shape and lesion-area feature extraction',
  'SVM / Random Forest / KNN comparison during development',
  'Disease prediction with decision-function margins',
  'Experimental Mild / Moderate / Severe lesion-area estimate',
]

const SEVERITY_BUCKETS = [
  { range: 'Less than 10%', label: 'Mild' },
  { range: '10% to less than 25%', label: 'Moderate' },
  { range: '25% or greater', label: 'Severe' },
]

/**
 * Development-only comparison recorded in
 * `data/processed/reproducibility/evaluation_report.json`.
 * Selection used CV macro F1; the held-out set was scored once, on the
 * selected SVM only, so it could not influence model choice.
 */
const CANDIDATE_RESULTS = [
  {
    name: 'RBF SVM',
    cvMacroF1: '0.8412 ± 0.0604',
    outOfFoldMacroF1: '0.8440',
    heldOutMacroF1: '0.7855',
    selected: true,
  },
  {
    name: 'Random Forest',
    cvMacroF1: '0.7935 ± 0.0387',
    outOfFoldMacroF1: '0.8006',
    heldOutMacroF1: null,
    selected: false,
  },
  {
    name: 'K-Nearest Neighbours',
    cvMacroF1: '0.7507 ± 0.0853',
    outOfFoldMacroF1: '0.7602',
    heldOutMacroF1: null,
    selected: false,
  },
]

function modelDisplayName(name: string): string {
  const normalised = name.toLowerCase()
  if (normalised === 'svm') return 'Support Vector Machine (SVM)'
  if (normalised === 'random_forest' || normalised === 'rf') return 'Random Forest'
  if (normalised === 'knn') return 'K-Nearest Neighbours'
  return name
}

export function AboutModelPage() {
  const { state, info, error, reload } = useModelInfo()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Model card"
        title="About Model"
        description="The loaded production bundle, the dataset it was trained on, how scores should be read, and the limitations that must remain visible."
      />

      {state === 'loading' ? (
        <section
          className="card flex items-center justify-center gap-3 px-6 py-14 text-sm text-ink-600"
          data-testid="model-info-loading"
        >
          <Spinner className="h-4 w-4 text-accent-600" />
          Loading model information from the backend…
        </section>
      ) : null}

      {state === 'error' && error ? (
        <div data-testid="model-info-error">
          <ErrorNotice error={error} onRetry={reload} />
        </div>
      ) : null}

      {state === 'success' && info ? (
        <div className="space-y-6" data-testid="model-info">
          <section className="card p-5" aria-labelledby="model-identity-heading">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="model-identity-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
                  {modelDisplayName(info.model_name)}
                </h2>
                <p className="mt-1 text-sm text-ink-600">
                  Selected during development from SVM, Random Forest and KNN by macro F1 on the
                  frozen cross-validation folds. The committed bundle is served unchanged. The live
                  SVM is configured with `C=1.0`, `gamma="scale"` and `class_weight="balanced"`.
                </p>
              </div>
              <span className="badge border-accent-200 bg-accent-50 text-accent-800">
                <ShieldIcon className="h-3.5 w-3.5" />
                {info.model_version}
              </span>
            </div>

            <MetricGrid>
              <Metric
                label="CV macro F1"
                value={`${formatDecimal(info.cv_macro_f1_mean, 3)} ± ${formatDecimal(
                  info.cv_macro_f1_std,
                  3,
                )}`}
                hint="Mean ± standard deviation across the 5 frozen folds"
              />
              <Metric
                label="Held-out macro F1"
                value={formatDecimal(info.held_out_macro_f1, 3)}
                hint={`${info.held_out_rows} images · evaluated once after selection`}
              />
              <Metric
                label="Development rows"
                value={info.training_rows}
                hint="Held-out test rows were never used for training or selection"
              />
              <Metric
                label="Feature vector"
                value={`${info.feature_count} features`}
                hint={`Version ${info.feature_set_version}`}
              />
            </MetricGrid>

            <dl className="mt-4 grid gap-3 text-xs text-ink-600 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="font-semibold text-ink-800">Bundle version</dt>
                <dd>{info.bundle_version}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Bundle exported</dt>
                <dd>{info.bundle_exported_at}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Dataset version</dt>
                <dd className="break-all font-mono text-[11px]">{info.dataset_version}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Split protocol</dt>
                <dd>{info.split_protocol}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Segmentation config</dt>
                <dd>{info.segmentation_config_version}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Quality config</dt>
                <dd>{info.quality_config_version}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">CV accuracy</dt>
                <dd>{formatDecimal(info.cv_accuracy_mean, 3)}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">CV balanced accuracy</dt>
                <dd>{formatDecimal(info.cv_balanced_accuracy_mean, 3)}</dd>
              </div>
              <div>
                <dt className="font-semibold text-ink-800">Held-out accuracy</dt>
                <dd>{formatDecimal(info.held_out_accuracy, 3)}</dd>
              </div>
            </dl>
            <p className="mt-3 rounded-md bg-ink-50 px-3 py-2 text-[11px] text-ink-500">
              Held-out status: {info.held_out_status}. The 24 held-out images are a single
              evaluation, not a tuning set; differences of roughly ±0.05–0.08 macro F1 are within
              sampling noise on a dataset this small.
            </p>
          </section>

          <section className="card p-5" aria-labelledby="candidate-comparison-heading">
            <h2
              id="candidate-comparison-heading"
              className="font-display text-xl font-medium tracking-tight text-ink-900"
            >
              Candidates compared during development
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              Three classical classifiers were trained on the same 50-feature vectors and the same
              frozen folds. The selected model is the one with the highest cross-validation macro F1.
            </p>
            <div className="mt-3 overflow-x-auto rounded-lg border border-ink-200">
              <table className="w-full min-w-[520px] text-sm">
                <caption className="sr-only">
                  Development cross-validation scores for the SVM, Random Forest and KNN candidates
                </caption>
                <thead>
                  <tr className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      Candidate
                    </th>
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      CV macro F1 (mean ± SD)
                    </th>
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      Out-of-fold macro F1
                    </th>
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      Held-out macro F1
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {CANDIDATE_RESULTS.map((candidate) => (
                    <tr
                      key={candidate.name}
                      className={`border-t border-ink-100 ${
                        candidate.selected ? 'bg-accent-50/60' : ''
                      }`}
                    >
                      <th scope="row" className="px-3 py-2 text-left font-semibold text-ink-900 sm:px-4">
                        <span className="flex flex-wrap items-center gap-2">
                          {candidate.name}
                          {candidate.selected ? (
                            <span className="rounded-full bg-accent-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                              Selected
                            </span>
                          ) : null}
                        </span>
                      </th>
                      <td className="px-3 py-2 font-mono text-xs text-ink-700 sm:px-4">
                        {candidate.cvMacroF1}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-ink-700 sm:px-4">
                        {candidate.outOfFoldMacroF1}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-ink-700 sm:px-4">
                        {candidate.heldOutMacroF1 ?? (
                          <span className="font-sans text-ink-500">Not evaluated</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-ink-500">
              Scores are development-only cross-validation results. Selection used CV macro F1
              alone; the 24-image held-out set was evaluated once, after selection, on the chosen
              SVM. Random Forest and KNN were therefore never scored on it, so the test set could
              not influence which model was selected.
            </p>
          </section>

          <section className="card p-5" aria-labelledby="score-reading-heading">
            <h2 id="score-reading-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
              How to read model scores
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Callout tone="info" title="Decision margins, not probabilities">
                <p>{info.score_note}</p>
                <p className="mt-2">
                  The API exposes <code className="font-mono">{info.score_kind}</code> values. There
                  is no <code className="font-mono">predict_proba</code>, no calibrated probability
                  and no confidence percentage.
                </p>
              </Callout>
              <Callout tone="neutral" title="What the UI shows">
                <p>
                  Per-class signed margins, the best-vs-second margin, and the class ranking. A
                  larger margin means the model preferred that class more strongly; it is not a
                  probability that the label is correct.
                </p>
                <p className="mt-2">
                  Calibrated probabilities: {info.calibrated_probabilities ? 'yes' : 'no'}.
                </p>
              </Callout>
            </div>
          </section>

          <section className="card p-5" aria-labelledby="supported-diseases-heading">
            <h2 id="supported-diseases-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
              Supported disease labels
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              Exactly three classes exist in the dataset and the model. There is no healthy class.
            </p>
            <ul className="mt-3 grid gap-3 sm:grid-cols-3">
              {SUPPORTED_DISEASES.map((disease) => (
                <li key={disease.slug} className="rounded-lg border border-ink-200 bg-ink-50/60 p-4">
                  <div className="flex items-center gap-2">
                    <LeafIcon className="h-4 w-4 text-accent-600" />
                    <h3 className="font-semibold text-ink-900">{disease.name}</h3>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-600">{disease.summary}</p>
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-wide text-ink-400">
                    {disease.slug}
                  </p>
                </li>
              ))}
            </ul>
            <div className="mt-4">
              <Callout tone="warning" title="No healthy-leaf result">
                <p>{HEALTHY_CAVEAT}</p>
              </Callout>
            </div>
          </section>

          <section className="card p-5" aria-labelledby="workflow-heading">
            <h2 id="workflow-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
              Required classical workflow
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              The professor-mandated pipeline from image input to experimental severity. No deep
              learning is used in Version 1.
            </p>
            <ol className="mt-3 grid gap-2 sm:grid-cols-2">
              {WORKFLOW.map((step, index) => (
                <li
                  key={step}
                  className="flex items-start gap-2 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-700"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink-900 text-[10px] font-semibold text-white">
                    {index + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </section>

          <section className="card p-5" aria-labelledby="dataset-heading">
            <h2 id="dataset-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
              Dataset and evaluation protocol
            </h2>
            <div className="mt-3 flex flex-col gap-2 rounded-xl border border-accent-200 bg-accent-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-700">
                  Dataset source
                </p>
                <p className="mt-0.5 text-sm font-semibold text-ink-900">{DATASET_SOURCE_NAME}</p>
              </div>
              <a
                href={DATASET_SOURCE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-accent-300 bg-white px-3 py-1.5 text-xs font-semibold text-accent-800 hover:bg-accent-50"
              >
                View on Kaggle
                <span aria-hidden="true">↗</span>
              </a>
            </div>
            <dl className="mt-3 grid gap-3 text-sm text-ink-600 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                  Dataset
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">120 rice-leaf images</dd>
                <dd className="text-xs">40 per disease class</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                  Cross-validation
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">96 development images</dd>
                <dd className="text-xs">5 group-aware folds</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                  Held-out test
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">24 images</dd>
                <dd className="text-xs">8 per class · singleton-only</dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                  Split protocol
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">{info.split_protocol}</dd>
                <dd className="text-xs">Frozen before model selection</dd>
              </div>
            </dl>
            <p className="mt-3 text-xs leading-relaxed text-ink-500">
              The dataset is a small, visually similar collection sourced from the public Kaggle
              release above; this project uses the approved 120-image subset. Confirmed duplicate
              groups never cross train/validation/test boundaries. The single held-out result
              carries substantial sampling uncertainty and is not a claim of field performance.
            </p>
          </section>

          <section className="card p-5" aria-labelledby="severity-heading">
            <h2 id="severity-heading" className="font-display text-xl font-medium tracking-tight text-ink-900">
              Experimental severity
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              Version 1 maps the measured visible-lesion area of the detected leaf onto three
              buckets. There are no expert severity labels and no validated agronomic thresholds.
            </p>
            <div className="mt-3 overflow-x-auto rounded-lg border border-ink-200">
              <table className="w-full min-w-[300px] text-sm">
                <caption className="sr-only">Experimental lesion-area severity buckets</caption>
                <thead>
                  <tr className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      Lesion area
                    </th>
                    <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                      Displayed severity
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {SEVERITY_BUCKETS.map((bucket) => (
                    <tr key={bucket.label} className="border-t border-ink-100">
                      <td className="px-3 py-2 text-ink-700 sm:px-4">{bucket.range}</td>
                      <td className="px-3 py-2 font-semibold text-ink-900 sm:px-4">
                        {bucket.label}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Callout tone="warning" title="Required severity disclaimer" className="mt-3 block">
              <p>{info.severity_disclaimer}</p>
            </Callout>
            <p className="mt-2 text-xs text-ink-500">
              Unreliable, missing or invalid lesion measurements produce <strong>no severity</strong>{' '}
              and <strong>no lesion percentage</strong>; they are never converted to 0% or Mild. A
              measured zero on a calibrated leaf remains a valid Mild result.
            </p>
          </section>

          <section className="card p-5" aria-labelledby="limitations-heading">
            <h2
              id="limitations-heading"
              className="flex items-center gap-2 font-display text-xl font-medium tracking-tight text-ink-900"
            >
              <AlertTriangleIcon className="h-5 w-5 text-warn-600" />
              Known limitations and failure cases
            </h2>
            <div className="mt-3">
              <Callout tone="danger" title="Not validated on smartphone or field photographs">
                <p>{SMARTPHONE_CAVEAT}</p>
              </Callout>
            </div>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-ink-600">
              {info.known_failure_cases.map((failure) => (
                <li key={failure}>{failure}</li>
              ))}
              <li>
                Severity is experimental and is not a validated agronomic grade; it must never be
                used for treatment decisions.
              </li>
              <li>
                History and artifacts are temporary and disappear on restart, expiry or clear. No
                uploaded image is stored permanently.
              </li>
              <li>
                Timing figures are CPU-only observations on a single development machine, not a
                production service-level guarantee.
              </li>
            </ul>
          </section>

          <Callout tone="neutral" title="Academic use only" className="block">
            <p>{GENERAL_DISCLAIMER}</p>
            <p className="mt-2">
              This model card is generated from the loaded bundle manifest; it does not retrain,
              recalibrate or recompute held-out metrics.
            </p>
          </Callout>
        </div>
      ) : null}
    </div>
  )
}
