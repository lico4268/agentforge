import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransportProvider } from '@/transport/TransportContext'
import { Dashboard } from '@/app/Dashboard'

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <TransportProvider>
        <Dashboard />
      </TransportProvider>
    </QueryClientProvider>,
  )
}

// Review finding 2: when the backend isn't running (the most common manual-check situation) or there
// are no arch.yaml files at all, an empty screen can't distinguish "not created yet" from "backend
// is down". Both states need an explicit message.
describe('Dashboard — arch list load states', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows an error banner when GET /api/arch fails (backend not running)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderDashboard()
    expect(await screen.findByText(/Failed to load arch file list/i)).toBeInTheDocument()
  })

  it('shows an explicit empty-state message when the list loads but is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    renderDashboard()
    expect(await screen.findByText(/No arch files found/i)).toBeInTheDocument()
  })
})
