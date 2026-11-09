import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BackendStatus, describeBackendConnection } from './BackendStatus'

const online = { state: 'online' as const, modelLoaded: true }

describe('backend connection status', () => {
  it('identifies a healthy local backend', () => {
    const view = describeBackendConnection(online, {
      apiBaseUrl: 'http://localhost:8000',
      configError: null,
    })

    expect(view.state).toBe('online')
    expect(view.label).toBe('Connected')
    expect(view.target).toBe('local')
    expect(view.targetLabel).toBe('Local')
    expect(view.detail).toContain('http://localhost:8000')
  })

  it('identifies a healthy Render backend', () => {
    const view = describeBackendConnection(online, {
      apiBaseUrl: 'https://dhanyadrishti-api.onrender.com',
      configError: null,
    })

    expect(view.state).toBe('online')
    expect(view.target).toBe('render')
    expect(view.targetLabel).toBe('Render')
  })

  it('explains a sleeping Render backend separately from a local outage', () => {
    const local = describeBackendConnection(
      { state: 'offline', modelLoaded: false },
      { apiBaseUrl: 'http://127.0.0.1:8000', configError: null },
    )
    expect(local.label).toBe('Backend offline')
    expect(local.detail).toMatch(/start the fastapi backend/i)

    const render = describeBackendConnection(
      { state: 'offline', modelLoaded: false },
      { apiBaseUrl: 'https://dhanyadrishti-api.onrender.com', configError: null },
    )
    expect(render.label).toBe('Render API offline')
    expect(render.detail).toMatch(/asleep/i)
    expect(render.detail).toMatch(/retries automatically/i)
  })

  it('distinguishes a loading model and an active health check', () => {
    expect(
      describeBackendConnection(
        { state: 'online', modelLoaded: false },
        { apiBaseUrl: 'http://localhost:8000', configError: null },
      ).label,
    ).toBe('API starting')

    expect(
      describeBackendConnection(
        { state: 'checking', modelLoaded: false },
        { apiBaseUrl: 'http://localhost:8000', configError: null },
      ).label,
    ).toBe('Checking API')
  })

  it('reports browser connectivity and configuration failures', () => {
    expect(
      describeBackendConnection(online, {
        apiBaseUrl: 'http://localhost:8000',
        configError: null,
        browserOnline: false,
      }).label,
    ).toBe("You're offline")

    expect(
      describeBackendConnection(online, {
        apiBaseUrl: 'http://localhost:8000',
        configError: 'Set VITE_API_BASE_URL and redeploy.',
      }).label,
    ).toBe('API not configured')
  })

  it('renders as a read-only status indicator with the target in its accessible name', () => {
    render(
      <BackendStatus
        health={online}
        apiBaseUrl="https://dhanyadrishti-api.onrender.com"
        configError={null}
      />,
    )

    const status = screen.getByTestId('backend-status')
    expect(status).toHaveAttribute('role', 'status')
    expect(status).toHaveTextContent('Connected')
    expect(status).toHaveTextContent('Render')
    expect(status).toHaveAttribute('data-target', 'render')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
