import type { ReactNode } from 'react'

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-700">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-ink-900 sm:text-4xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-600">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
