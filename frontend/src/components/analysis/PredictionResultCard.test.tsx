import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { makePrediction } from '../../test/fixtures'
import { SEVERITY_DISCLAIMER, UNCERTAIN_NOTICE } from '../../utils/disclaimers'
import { PredictionResultCard } from './PredictionResultCard'

describe('PredictionResultCard', () => {
  it('shows the label, decision margins, lesion area and severity disclaimer', () => {
    render(<PredictionResultCard prediction={makePrediction()} />)

    expect(screen.getByRole('heading', { name: 'Brown Spot' })).toBeInTheDocument()
    expect(screen.getByText('Predicted')).toBeInTheDocument()
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('Moderate')
    expect(screen.getByTestId('severity-disclaimer')).toHaveTextContent(SEVERITY_DISCLAIMER)
    expect(screen.getByText('12.4%')).toBeInTheDocument()

    expect(screen.getByText('Model scores (decision margins)')).toBeInTheDocument()
    expect(screen.getByText('+1.31')).toBeInTheDocument()
    expect(screen.getByTestId('decision-margin')).toHaveTextContent('+1.13')
    expect(screen.getByText(/not probabilities or percentages/i)).toBeInTheDocument()

    // There must be no confidence field or confidence percentage anywhere.
    expect(screen.queryByText(/^confidence\b/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/confidence\s*[:=]\s*\d/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bconfidence\s+\d/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\d+% confidence/i)).not.toBeInTheDocument()
  })

  it('previews temporary artifacts in-app instead of downloading them', async () => {
    const user = userEvent.setup()
    render(<PredictionResultCard prediction={makePrediction()} />)

    const original = screen.getByRole('button', {
      name: /preview oriented upload artifact/i,
    })
    expect(original).not.toHaveAttribute('href')
    expect(screen.getByRole('button', { name: /preview leaf mask artifact/i })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /preview lesion mask artifact/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/current backend session/i)).toBeInTheDocument()

    await user.click(original)

    const dialog = screen.getByRole('dialog', { name: /oriented upload preview/i })
    expect(within(dialog).getByTestId('artifact-full-image')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /^download$/i })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /close preview/i })).toBeInTheDocument()
  })

  it('renders an uncertain label as unconfirmed using the required PRD text', () => {
    render(<PredictionResultCard prediction={makePrediction({ status: 'uncertain' })} />)

    expect(screen.getByTestId('prediction-result')).toHaveAttribute('data-status', 'uncertain')
    expect(screen.getByText('Uncertain')).toBeInTheDocument()
    expect(screen.getByText(UNCERTAIN_NOTICE)).toBeInTheDocument()
    expect(
      screen.getByText('Unconfirmed pattern — this is not a diagnosis.'),
    ).toBeInTheDocument()
  })

  it('never turns an unreliable lesion into 0% or Mild', () => {
    render(
      <PredictionResultCard
        prediction={makePrediction({
          lesion_area_percentage: null,
          lesion_reliable: false,
          severity: null,
          severity_reason_code: 'LESION_ESTIMATE_UNRELIABLE',
        })}
      />,
    )

    expect(screen.getByText('Not available')).toBeInTheDocument()
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('Not reported')
    expect(screen.getByTestId('severity-note')).toHaveTextContent(/unreliable/i)
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument()
    expect(screen.queryByText('Mild')).not.toBeInTheDocument()
    expect(screen.getByText(/not converted to 0%/i)).toBeInTheDocument()
  })

  it('surfaces warnings and missing features', () => {
    render(
      <PredictionResultCard
        prediction={makePrediction({
          warnings: ['BLURRY_IMAGE', 'MULTIPLE_LEAVES'],
          missing_features: ['lesion_area_ratio', 'lesion_mean_ratio'],
        })}
      />,
    )

    expect(screen.getByTestId('quality-warnings')).toHaveTextContent(/appears blurry/i)
    expect(screen.getByTestId('quality-warnings')).toHaveTextContent(/multiple leaf regions/i)
    expect(screen.getByText(/missing feature values/i)).toBeInTheDocument()
    expect(screen.getByText('lesion_area_ratio')).toBeInTheDocument()
    expect(screen.getByText(/not.*replaced with zero/i)).toBeInTheDocument()
  })

  it('refuses to present a healthy value as a disease result', () => {
    render(<PredictionResultCard prediction={makePrediction({ disease: 'healthy' })} />)

    expect(screen.getByRole('heading', { name: 'Unsupported label' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Healthy' })).not.toBeInTheDocument()
  })
})
