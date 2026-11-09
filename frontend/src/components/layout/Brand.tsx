/**
 * DhanyaDrishti brand mark: a rice leaf with a grain spine and a scan dot,
 * suggesting both the crop and the diagnostic pipeline.
 */
export function BrandMark({ className = 'h-10 w-10' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      className={className}
      role="img"
      aria-label="DhanyaDrishti logo"
      focusable="false"
    >
      <defs>
        <linearGradient id="dd-brand-mark" x1="6" y1="2" x2="42" y2="46" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4ade80" />
          <stop offset="0.55" stopColor="#10b981" />
          <stop offset="1" stopColor="#047857" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="44" height="44" rx="14" fill="url(#dd-brand-mark)" />
      <rect
        x="2"
        y="2"
        width="44"
        height="44"
        rx="14"
        fill="none"
        stroke="rgba(255,255,255,0.28)"
        strokeWidth="1"
      />
      <path
        d="M24 38c0-8.6 5.1-14.7 12.2-16.7-1.3 9.1-5.9 14.2-12.2 16.7Z"
        fill="#ffffff"
        opacity="0.96"
      />
      <path
        d="M24 38c0-7.9-4.5-13.6-11.2-15.4 1.3 8.4 5.1 13 11.2 15.4Z"
        fill="#ffffff"
        opacity="0.7"
      />
      <path d="M24 38V28.4" stroke="#064e3b" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="24" cy="25.4" r="2" fill="#064e3b" />
    </svg>
  )
}
