import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { makeRejected } from '../../test/fixtures'
import { RejectedResultCard } from './RejectedResultCard'

describe('RejectedResultCard', () => {
  it('shows the rejection reason without any prediction fields', async () => {
    const user = userEvent.setup()
    const onChooseAnother = vi.fn()
    render(
      <RejectedResultCard
        rejection={makeRejected()}
        onChooseAnother={onChooseAnother}
      />,
    )

    expect(screen.getByTestId('rejected-result')).toHaveTextContent(
      /no suitable rice leaf region/i,
    )
    expect(screen.getByText('NO_CLEAR_LEAF_FOUND')).toBeInTheDocument()
    expect(screen.getByText(/no disease label was assigned/i)).toBeInTheDocument()
    expect(screen.getByText(/not added to temporary prediction history/i)).toBeInTheDocument()

    expect(screen.queryByTestId('prediction-result')).not.toBeInTheDocument()
    expect(screen.queryByTestId('score-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('severity-badge')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /brown spot/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /choose another image/i }))
    expect(onChooseAnother).toHaveBeenCalledTimes(1)
  })
})
