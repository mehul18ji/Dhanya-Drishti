import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ImageUploader } from './ImageUploader'
import { makeFile } from '../../test/fixtures'

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('file input not found')
  return input
}

describe('ImageUploader', () => {
  it('accepts a valid image through the file picker', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <ImageUploader file={null} onFileSelected={onFileSelected} />,
    )
    const file = makeFile({ name: 'leaf.png', type: 'image/png' })

    fireEvent.change(fileInput(container), { target: { files: [file] } })

    expect(onFileSelected).toHaveBeenCalledWith(file)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('rejects an unsupported type before calling the backend', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <ImageUploader file={null} onFileSelected={onFileSelected} />,
    )

    fireEvent.change(fileInput(container), {
      target: { files: [makeFile({ name: 'leaf.gif', type: 'image/gif' })] },
    })

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/unsupported file type/i)
  })

  it('rejects an oversize image with a readable message', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <ImageUploader file={null} onFileSelected={onFileSelected} />,
    )

    fireEvent.change(fileInput(container), {
      target: { files: [makeFile({ size: 12 * 1024 * 1024 })] },
    })

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/limit is 10 MB/i)
  })

  it('opens the picker from an accessible button', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ImageUploader file={null} onFileSelected={vi.fn()} />,
    )
    const clickSpy = vi.spyOn(fileInput(container), 'click').mockImplementation(() => {})

    await user.click(screen.getByRole('button', { name: /browse files/i }))

    expect(clickSpy).toHaveBeenCalledTimes(1)
  })

  it('disables selection while an analysis is running', () => {
    const { container } = render(
      <ImageUploader file={makeFile()} onFileSelected={vi.fn()} disabled />,
    )
    expect(screen.getByRole('button', { name: /browse files/i })).toBeDisabled()
    expect(fileInput(container)).toBeDisabled()
  })
})
