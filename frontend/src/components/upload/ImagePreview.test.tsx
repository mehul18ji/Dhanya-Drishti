import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ImagePreview } from './ImagePreview'
import { makeFile } from '../../test/fixtures'

function setNaturalSize(image: HTMLElement, width: number, height: number) {
  Object.defineProperty(image, 'naturalWidth', { configurable: true, value: width })
  Object.defineProperty(image, 'naturalHeight', { configurable: true, value: height })
  fireEvent.load(image)
}

describe('ImagePreview', () => {
  it('renders a portrait preview without stretching', () => {
    render(<ImagePreview file={makeFile({ name: 'portrait.jpg' })} onRemove={vi.fn()} />)
    const image = screen.getByRole('img', { name: /preview of the selected leaf/i })
    expect(image).toHaveClass('object-contain')

    setNaturalSize(image, 600, 1200)

    expect(screen.getByTestId('preview-dimensions')).toHaveTextContent('600 × 1200 px')
    expect(screen.getByTestId('preview-orientation')).toHaveTextContent('Portrait')
    expect(screen.getByText('portrait.jpg')).toBeInTheDocument()
  })

  it('labels a landscape preview correctly', () => {
    render(<ImagePreview file={makeFile({ name: 'landscape.jpg' })} onRemove={vi.fn()} />)
    const image = screen.getByRole('img', { name: /preview of the selected leaf/i })
    setNaturalSize(image, 1600, 900)

    expect(screen.getByTestId('preview-dimensions')).toHaveTextContent('1600 × 900 px')
    expect(screen.getByTestId('preview-orientation')).toHaveTextContent('Landscape')
  })

  it('opens a full-screen preview without downloading the image', async () => {
    const user = userEvent.setup()
    render(<ImagePreview file={makeFile({ name: 'leaf.jpg' })} onRemove={vi.fn()} />)

    await user.click(
      screen.getByRole('button', { name: /open full-screen preview of leaf\.jpg/i }),
    )

    const dialog = screen.getByRole('dialog', { name: /selected image preview/i })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByTestId('artifact-full-image')).toHaveAttribute(
      'src',
      expect.stringContaining('blob:'),
    )
    expect(screen.getByRole('button', { name: /^download$/i })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('removes the selected image through an accessible button', async () => {
    const user = userEvent.setup()
    const onRemove = vi.fn()
    render(<ImagePreview file={makeFile()} onRemove={onRemove} />)

    await user.click(screen.getByRole('button', { name: /remove selected image/i }))

    expect(onRemove).toHaveBeenCalledTimes(1)
  })
})
