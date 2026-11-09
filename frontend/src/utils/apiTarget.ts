export type ApiTarget = 'local' | 'render' | 'hosted'

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

/** Classify the configured API origin so the UI can name the connection source. */
export function resolveApiTarget(baseUrl: string): ApiTarget {
  try {
    const hostname = new URL(baseUrl).hostname.replace(/^\[|\]$/g, '').toLowerCase()
    if (LOOPBACK_HOSTS.has(hostname) || hostname.endsWith('.localhost')) return 'local'
    if (hostname === 'onrender.com' || hostname.endsWith('.onrender.com')) return 'render'
    return 'hosted'
  } catch {
    return 'hosted'
  }
}

export function apiTargetLabel(target: ApiTarget): string {
  if (target === 'local') return 'Local'
  if (target === 'render') return 'Render'
  return 'Hosted'
}
