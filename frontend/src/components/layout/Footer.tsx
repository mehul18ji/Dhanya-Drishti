import { DATASET_SOURCE_NAME, DATASET_SOURCE_URL } from '../../utils/disclaimers'

export function Footer() {
  return (
    <footer className="mt-auto border-t border-ink-200 bg-white/70 pb-[max(1.25rem,env(safe-area-inset-bottom))] backdrop-blur">
      <div className="mx-auto w-full max-w-7xl space-y-2 px-4 py-5 text-[11px] leading-relaxed text-ink-500 sm:px-6 sm:text-xs lg:px-8">
        <p>
          <span className="font-semibold text-ink-700">DhanyaDrishti</span> is an academic prototype
          trained on a 120-image subset of the{' '}
          <a
            href={DATASET_SOURCE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-accent-700 underline decoration-accent-300 underline-offset-2 hover:text-accent-800"
          >
            {DATASET_SOURCE_NAME}
          </a>
          . It supports only Bacterial Leaf Blight, Brown Spot and Leaf Smut.
        </p>
        <p>
          There is no healthy class, and no smartphone or field-camera validation has been
          performed. Severity is an experimental estimate based on the visible lesion area in the
          uploaded image; it is not a validated agronomic grade. Results must not replace
          agricultural experts, field inspection or plant-pathology diagnosis.
        </p>
      </div>
    </footer>
  )
}
