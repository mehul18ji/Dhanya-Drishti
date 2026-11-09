/**
 * Download a temporary artifact only when the user explicitly asks for it.
 *
 * The backend serves these PNGs with `Content-Disposition: attachment`, so a
 * plain link or `target="_blank"` saves the file. Fetching the bytes and using
 * an object URL keeps preview and download as two separate, intentional actions.
 */
export async function downloadArtifact(url: string, filename: string): Promise<void> {
  const response = await fetch(url, { credentials: 'omit' })
  if (!response.ok) {
    throw new Error(`Artifact download failed with HTTP ${response.status}.`)
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = safeFilename(filename)
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
}

function safeFilename(filename: string): string {
  const cleaned = filename.trim().replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '')
  return cleaned.length > 0 ? cleaned : 'artifact.png'
}

/** A readable PNG filename for labels such as "Leaf mask". */
export function artifactFilename(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'artifact'}.png`
}
