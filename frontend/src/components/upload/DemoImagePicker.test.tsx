import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DEMO_IMAGES, DemoImagePicker, demoImageUrl } from './DemoImagePicker'

/** Minimal fetch-response stand-in: jsdom has no real network stack. */
function blobResponse(blob: Blob, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    blob: () => Promise.resolve(blob),
  } as unknown as Response
}

const jpeg = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], { type: 'image/jpeg' })

describe('DemoImagePicker', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders one accessible tile per bundled demo leaf', () => {
    render(<DemoImagePicker onFileSelected={vi.fn()} />)

    expect(screen.getByTestId('demo-image-picker')).toBeInTheDocument()
    expect(DEMO_IMAGES).toHaveLength(3)
    for (const image of DEMO_IMAGES) {
      expect(screen.getByRole('button', { name: `Use ${image.label}` })).toBeInTheDocument()
    }
  })

  it('serves the images from the app bundle, not the repository', () => {
    expect(demoImageUrl(DEMO_IMAGES[0])).toBe('/demo/demo-image-1.jpg')
    expect(demoImageUrl(DEMO_IMAGES[2])).toBe('/demo/demo-image-3.jpg')
  })

  it('keeps the demo names neutral so they cannot reveal the expected label', () => {
    for (const image of DEMO_IMAGES) {
      expect(image.label).toMatch(/^Demo Image [123]$/)
      expect(image.filename).toMatch(/^demo-image-[123]\.jpg$/)
      expect(`${image.label} ${image.filename} ${image.alt}`).not.toMatch(
        /bacterial|blight|brown|spot|smut|leaf blight/i,
      )
    }
  })

  it('hands a real File to the normal upload flow when a tile is chosen', async () => {
    const user = userEvent.setup()
    const onFileSelected = vi.fn()
    fetchMock.mockResolvedValue(blobResponse(jpeg()))

    render(<DemoImagePicker onFileSelected={onFileSelected} />)
    await user.click(screen.getByRole('button', { name: 'Use Demo Image 2' }))

    await waitFor(() => expect(onFileSelected).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenCalledWith('/demo/demo-image-2.jpg', {
      cache: 'no-store',
    })

    const file = onFileSelected.mock.calls[0][0] as File
    expect(file).toBeInstanceOf(File)
    expect(file.name).toBe('demo-image-2.jpg')
    expect(file.type).toBe('image/jpeg')
    expect(file.size).toBeGreaterThan(0)
  })

  it('marks the selected demo tile without loading anything on mount', () => {
    render(
      <DemoImagePicker onFileSelected={vi.fn()} selectedName="demo-image-3.jpg" />,
    )

    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Use Demo Image 3' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: 'Use Demo Image 2' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('does not fetch while disabled (analysis running or backend unavailable)', async () => {
    const user = userEvent.setup()
    render(<DemoImagePicker onFileSelected={vi.fn()} disabled />)

    const tile = screen.getByRole('button', { name: 'Use Demo Image 2' })
    expect(tile).toBeDisabled()
    await user.click(tile)

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('reports a failed demo load instead of silently doing nothing', async () => {
    const user = userEvent.setup()
    const onFileSelected = vi.fn()
    fetchMock.mockRejectedValue(new Error('offline'))

    render(<DemoImagePicker onFileSelected={onFileSelected} />)
    await user.click(screen.getByRole('button', { name: 'Use Demo Image 1' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/i)
    expect(onFileSelected).not.toHaveBeenCalled()
  })

  it('rejects a demo asset the server answers with an error status', async () => {
    const user = userEvent.setup()
    const onFileSelected = vi.fn()
    fetchMock.mockResolvedValue(blobResponse(jpeg(), 404))

    render(<DemoImagePicker onFileSelected={onFileSelected} />)
    await user.click(screen.getByRole('button', { name: 'Use Demo Image 3' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/i)
    expect(onFileSelected).not.toHaveBeenCalled()
  })
})
