const diseases = [
  {
    name: 'Bacterial Leaf Blight',
    description: 'Water-soaked streaks that enlarge into pale, dry lesions along the leaf blade.',
  },
  {
    name: 'Brown Spot',
    description: 'Oval brown lesions, often with a lighter centre, scattered across the leaf.',
  },
  {
    name: 'Leaf Smut',
    description: 'Small dark, slightly raised spots distributed over the leaf surface.',
  },
]

const workflow = [
  'Image input and validation',
  'Preprocessing',
  'Resizing without distortion',
  'Noise removal',
  'RGB → HSV and/or Lab conversion',
  'Leaf segmentation',
  'Disease-region segmentation',
  'Colour, texture, shape and lesion-area feature extraction',
  'SVM / Random Forest / KNN comparison',
  'Disease prediction',
  'Mild / Moderate / Severe intensity estimate',
]

const limitations = [
  'No healthy-leaf class exists in the dataset; the system cannot diagnose a leaf as healthy.',
  'Only Bacterial Leaf Blight, Brown Spot and Leaf Smut are supported.',
  'The dataset has 120 images, so validation scores are not evidence of field reliability.',
  'Severity is an experimental lesion-area estimate, not an agronomist grade.',
  'Behaviour on smartphone photos, unusual lighting, background clutter or multiple leaves may differ from dataset images.',
]

export function AboutModelPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">About Model</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-600">
          Transparent information about the dataset, the required classical workflow, the selected
          classifier and the limits of this prototype.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2" aria-labelledby="diseases-heading">
          <h2 id="diseases-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Supported diseases
          </h2>
          <ul className="mt-3 space-y-3">
            {diseases.map((disease) => (
              <li key={disease.name} className="rounded-lg border border-ink-100 bg-ink-50/50 p-3">
                <p className="text-sm font-semibold text-ink-800">{disease.name}</p>
                <p className="mt-0.5 text-xs text-ink-600">{disease.description}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-5" aria-labelledby="dataset-heading">
          <h2 id="dataset-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Dataset
          </h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Total images</dt>
              <dd className="font-semibold text-ink-900">120</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Images per class</dt>
              <dd className="font-semibold text-ink-900">40</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Healthy class</dt>
              <dd className="font-semibold text-ink-900">Not supported</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Severity labels</dt>
              <dd className="font-semibold text-ink-900">None</dd>
            </div>
          </dl>
          <p className="mt-3 border-t border-ink-100 pt-3 text-xs leading-relaxed text-ink-500">
            Source: the approved Kaggle Rice Leaf Diseases dataset. Raw images are kept out of version
            control and are never modified.
          </p>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5" aria-labelledby="workflow-heading">
          <h2 id="workflow-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Required classical workflow
          </h2>
          <ol className="mt-3 space-y-1.5">
            {workflow.map((stage, index) => (
              <li key={stage} className="flex items-start gap-2 text-sm text-ink-600">
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-ink-100 text-[10px] font-semibold text-ink-600"
                >
                  {index + 1}
                </span>
                {stage}
              </li>
            ))}
          </ol>
        </section>

        <section className="card p-5" aria-labelledby="status-heading">
          <h2 id="status-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Model status
          </h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Model version</dt>
              <dd className="font-semibold text-ink-900">Not trained yet</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Selected classifier</dt>
              <dd className="font-semibold text-ink-900">Chosen after evaluation</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Selection metric</dt>
              <dd className="font-semibold text-ink-900">Macro F1-score</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-600">Severity method</dt>
              <dd className="font-semibold text-ink-900">Experimental lesion area</dd>
            </div>
          </dl>
          <p className="mt-3 border-t border-ink-100 pt-3 text-xs leading-relaxed text-ink-500">
            Training, comparison of SVM / Random Forest / KNN and artifact export happen in Phase 3.
            Metrics will be published here from the evaluation report once available.
          </p>
        </section>
      </div>

      <section className="card p-5" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading" className="text-sm font-semibold uppercase tracking-wide text-ink-500">
          Known limitations
        </h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {limitations.map((limitation) => (
            <li key={limitation} className="flex gap-2 text-sm text-ink-600">
              <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full bg-warn-500" />
              {limitation}
            </li>
          ))}
        </ul>
      </section>

      <div className="rounded-xl border border-ink-200 bg-white p-4 text-xs leading-relaxed text-ink-500">
        <span className="font-semibold text-ink-700">Disclaimer.</span> DhanyaDrishti is an academic
        prototype. Its severity output is an experimental visible-lesion-area estimate. It must not be
        presented as a replacement for agricultural experts, field inspection or plant-pathology
        diagnosis.
      </div>
    </div>
  )
}
