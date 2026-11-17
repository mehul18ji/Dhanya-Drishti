/**
 * DhanyaDrishti brand mark: the project logo, served from `public/` so the
 * header, error screen and documentation all use the same artwork.
 */
export function BrandMark({ className = 'h-10 w-10' }: { className?: string }) {
  return (
    <img
      src="/dhanyadrishti-logo.png"
      alt="DhanyaDrishti logo"
      className={`${className} object-contain`}
      draggable={false}
    />
  )
}
