import { createContext, useContext, type ReactNode } from 'react'

import { useHealth, type HealthState } from './useHealth'

export const BackendHealthContext = createContext<HealthState | null>(null)

/** One shared health poll for the header indicator and every page. */
export function BackendHealthProvider({ children }: { children: ReactNode }) {
  const health = useHealth()

  return <BackendHealthContext.Provider value={health}>{children}</BackendHealthContext.Provider>
}

export function useBackendHealth(): HealthState {
  const health = useContext(BackendHealthContext)
  if (!health) {
    throw new Error('useBackendHealth must be used inside BackendHealthProvider')
  }
  return health
}
