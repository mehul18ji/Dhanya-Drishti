import { DEFAULT_UPLOAD_LIMIT_MB } from '../services/api'

export const ACCEPTED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp'] as const
export const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const
export const ACCEPT_ATTRIBUTE =
  '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp'

export interface UploadCheck {
  ok: boolean
  error: string | null
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
}

/**
 * Client-side pre-check that mirrors the backend's upload rules.
 *
 * This is a convenience only: the backend still performs the authoritative
 * extension, MIME, decode and dimension validation.
 */
export function validateUploadFile(
  file: File,
  maxSizeMb: number = DEFAULT_UPLOAD_LIMIT_MB,
): UploadCheck {
  if (file.size === 0) {
    return { ok: false, error: 'This file is empty. Choose a non-empty image file.' }
  }

  const extension = extensionOf(file.name)
  if (!ACCEPTED_EXTENSIONS.includes(extension as (typeof ACCEPTED_EXTENSIONS)[number])) {
    return {
      ok: false,
      error: 'Unsupported file type. Upload a JPG, JPEG, PNG or WEBP image.',
    }
  }

  if (
    file.type &&
    !ACCEPTED_MIME_TYPES.includes(file.type as (typeof ACCEPTED_MIME_TYPES)[number])
  ) {
    return {
      ok: false,
      error: 'The browser reports an unsupported image format. Upload a JPG, JPEG, PNG or WEBP image.',
    }
  }

  const limitBytes = maxSizeMb * 1024 * 1024
  if (file.size > limitBytes) {
    return {
      ok: false,
      error: `This image is ${(file.size / (1024 * 1024)).toFixed(1)} MB. The limit is ${maxSizeMb} MB.`,
    }
  }

  return { ok: true, error: null }
}
