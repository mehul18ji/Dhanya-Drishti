import { warningMessage } from '../../utils/warnings'
import { Callout } from '../common/Callout'

export function QualityWarningCard({ codes }: { codes: string[] }) {
  if (codes.length === 0) return null
  return (
    <div data-testid="quality-warnings">
      <Callout tone="warning" title={`Quality warnings (${codes.length})`}>
        <p>
          The image was analysed, but these conditions may reduce reliability. Treat the label and
          severity as less certain.
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {codes.map((code) => (
            <li key={code}>
              {warningMessage(code)}{' '}
              <span className="font-mono text-[10px] uppercase tracking-wide text-ink-500">
                {code}
              </span>
            </li>
          ))}
        </ul>
      </Callout>
    </div>
  )
}

export function MissingFeaturesCard({ features }: { features: string[] }) {
  if (features.length === 0) return null
  return (
    <Callout
      tone="warning"
      title={`Missing feature values (${features.length})`}
      className="block"
    >
      <p>
        Some lesion-dependent features could not be measured. The committed model pipeline imputes
        them from training data; they are <strong>not</strong> replaced with zero here and the
        image is not dropped.
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {features.map((feature) => (
          <li
            key={feature}
            className="rounded border border-warn-300 bg-white px-1.5 py-0.5 font-mono text-[11px] text-ink-700"
          >
            {feature}
          </li>
        ))}
      </ul>
    </Callout>
  )
}
