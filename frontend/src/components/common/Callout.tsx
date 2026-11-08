import type { ReactNode } from 'react'

import { AlertTriangleIcon, CheckCircleIcon, InfoIcon, XCircleIcon } from './Icons'

type Tone = 'info' | 'success' | 'warning' | 'danger' | 'neutral'

const TONES: Record<
  Tone,
  { wrapper: string; icon: string; title: string; Icon: typeof InfoIcon }
> = {
  info: {
    wrapper: 'border-sky-200 bg-sky-50',
    icon: 'text-sky-600',
    title: 'text-sky-900',
    Icon: InfoIcon,
  },
  success: {
    wrapper: 'border-accent-200 bg-accent-50',
    icon: 'text-accent-600',
    title: 'text-accent-900',
    Icon: CheckCircleIcon,
  },
  warning: {
    wrapper: 'border-warn-300 bg-warn-50',
    icon: 'text-warn-700',
    title: 'text-warn-900',
    Icon: AlertTriangleIcon,
  },
  danger: {
    wrapper: 'border-red-200 bg-red-50',
    icon: 'text-red-600',
    title: 'text-red-900',
    Icon: XCircleIcon,
  },
  neutral: {
    wrapper: 'border-ink-200 bg-ink-50',
    icon: 'text-ink-500',
    title: 'text-ink-800',
    Icon: InfoIcon,
  },
}

export function Callout({
  tone = 'info',
  title,
  children,
  role,
  className = '',
}: {
  tone?: Tone
  title?: string
  children: ReactNode
  role?: 'alert' | 'status'
  className?: string
}) {
  const styles = TONES[tone]
  const { Icon } = styles
  return (
    <div
      role={role}
      className={`flex gap-3 rounded-lg border px-4 py-3 text-sm leading-relaxed ${styles.wrapper} ${className}`}
    >
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${styles.icon}`} />
      <div className="min-w-0 space-y-1">
        {title ? (
          <p className={`font-semibold ${styles.title}`}>{title}</p>
        ) : null}
        <div className="text-ink-700">{children}</div>
      </div>
    </div>
  )
}
