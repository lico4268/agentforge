import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransportProvider } from '@/transport/TransportContext'
import { useExecutionStore } from '@/execution/useExecutionStore'
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

// round 2 fix: runError reached the store (e.g. MockTransport's archFile-only-run
// message, or a real backend's WS "error") but Dashboard never rendered it — Run
// looked completely inert. Now it uses the same red-banner treatment as
// archError/archListError, and clears itself because it's a live read of the
// store rather than something Dashboard remembers on its own.
describe('Dashboard — runError banner', () => {
  beforeEach(() => {
    // 파일 목록 배너가 같이 뜨는 걸 막아 이 테스트의 관심사(runError)만 본다.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    useExecutionStore.getState().reset()
  })

  it('renders a visible banner containing the message', () => {
    useExecutionStore.setState({ runStatus: 'error', runError: 'Execution error: boom' })
    renderDashboard()
    expect(screen.getByText('Execution error: boom')).toBeInTheDocument()
  })

  it('disappears once the store is reset', () => {
    useExecutionStore.setState({ runStatus: 'error', runError: 'Execution error: boom' })
    renderDashboard()
    expect(screen.getByText('Execution error: boom')).toBeInTheDocument()

    act(() => {
      useExecutionStore.getState().reset()
    })
    expect(screen.queryByText('Execution error: boom')).not.toBeInTheDocument()
  })

  it('disappears once a new run starts (setRunState clears it)', () => {
    useExecutionStore.setState({ runStatus: 'error', runError: 'Execution error: boom' })
    renderDashboard()
    expect(screen.getByText('Execution error: boom')).toBeInTheDocument()

    act(() => {
      useExecutionStore.getState().setRunState({ runId: 'run-2', status: 'running', result: null })
    })
    expect(screen.queryByText('Execution error: boom')).not.toBeInTheDocument()
  })
})
