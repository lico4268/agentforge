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

// 리뷰 finding 2: 백엔드가 안 떠 있거나(가장 흔한 수동 검증 상황) arch.yaml이
// 하나도 없을 때 화면이 그냥 비어있으면 "아직 안 만들어진 건지 backend가 죽은
// 건지" 구분할 수 없다. 두 상태 모두 명시적인 안내가 있어야 한다.
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
