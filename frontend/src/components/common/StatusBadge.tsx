import type { HistoryStatus } from '../../types/api'
import { AlertTriangleIcon, CheckCircleIcon, XCircleIcon } from './Icons'

const CONFIG: Record<
  HistoryStatus,
  { label: string; className: string; Icon: typeof CheckCircleIcon }
> = {
  predicted: {
    label: 'Predicted',
    className: 'border-accent-200 bg-accent-50 text-accent-800',
    Icon: CheckCircleIcon,
  },
  uncertain: {
    label: 'Uncertain',
    className: 'border-warn-300 bg-warn-50 text-warn-800',
    Icon: AlertTriangleIcon,
  },
  rejected: {
    label: 'Rejected',
    className: 'border-ink-300 bg-ink-100 text-ink-700',
    Icon: XCircleIcon,
  },
}

export function StatusBadge({ status }: { status: HistoryStatus }) {
  const { label, className, Icon } = CONFIG[status]
  return (
    <span className={`badge ${className}`} data-status={status}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  )
}
