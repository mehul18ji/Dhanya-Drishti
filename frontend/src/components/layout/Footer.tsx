export function Footer() {
  return (
    <footer className="mt-auto border-t border-ink-200 bg-white">
      <div className="mx-auto w-full max-w-7xl space-y-2 px-4 py-5 text-xs leading-relaxed text-ink-500 sm:px-6 lg:px-8">
        <p>
          <span className="font-semibold text-ink-700">DhanyaDrishti</span> is an academic prototype
          trained on a small dataset of 120 diseased rice-leaf images. It supports only Bacterial Leaf
          Blight, Brown Spot and Leaf Smut.
        </p>
        <p>
          Severity is an experimental estimate based on the visible lesion area in the uploaded image.
          It is not a validated agronomic severity grade. Results must not replace agricultural
          experts, field inspection or plant-pathology diagnosis.
        </p>
      </div>
    </footer>
  )
}
