import { useEffect, useState } from 'react'

/**
 * Create and revoke an object URL for a selected file. Keeps portrait and
 * landscape aspects intact because the preview itself uses `object-contain`.
 */
export function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setUrl(null)
      return
    }
    const next = URL.createObjectURL(file)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [file])

  return url
}
