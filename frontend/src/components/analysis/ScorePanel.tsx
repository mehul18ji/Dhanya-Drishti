import { diseaseLabel } from '../../utils/diseases'
import { formatScore } from '../../utils/format'

/**
 * Decision-function margins, never probabilities or confidence percentages.
 * The table deliberately shows raw signed margins and an explicit note.
 */
export function ScorePanel({
  scores,
  ranking,
  margin,
  scoreNote,
}: {
  scores: Record<string, number>
  ranking: string[]
  margin: number | null
  scoreNote: string
}) {
  const ordered =
    ranking.length > 0
      ? ranking
      : Object.entries(scores)
          .sort(([, left], [, right]) => right - left)
          .map(([label]) => label)

  return (
    <section className="rounded-lg border border-ink-200 bg-white" data-testid="score-panel">
      <div className="border-b border-ink-200 px-4 py-3">
        <h3 className="text-sm font-semibold text-ink-900">Model scores (decision margins)</h3>
        <p className="mt-1 text-xs leading-relaxed text-ink-500">
          These are one-vs-rest <code className="font-mono">decision_function</code> values.
          They are not probabilities or percentages. A larger value means more support for that
          class; only the ranking and best-vs-second margin are meaningful here.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[300px] text-sm">
          <caption className="sr-only">
            Per-class decision-function margins for the three supported rice-leaf diseases
          </caption>
          <thead>
            <tr className="border-b border-ink-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
              <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                Rank
              </th>
              <th scope="col" className="px-3 py-2 font-semibold sm:px-4">
                Supported class
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold sm:px-4">
                Decision score
              </th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((label, index) => {
              const value = scores[label]
              return (
                <tr
                  key={label}
                  className={index === 0 ? 'bg-accent-50/60' : 'border-t border-ink-100'}
                >
                  <td className="px-3 py-2 tabular-nums text-ink-500 sm:px-4">{index + 1}</td>
                  <td className="px-3 py-2 font-medium text-ink-800 sm:px-4">
                    {diseaseLabel(label)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums text-ink-900 sm:px-4">
                    {formatScore(value)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-1 border-t border-ink-200 bg-ink-50 px-4 py-3 text-xs text-ink-600">
        <p>
          Best-vs-second margin:{' '}
          <span className="font-mono font-semibold text-ink-900" data-testid="decision-margin">
            {formatScore(margin)}
          </span>
        </p>
        <p>{scoreNote}</p>
      </div>
    </section>
  )
}
