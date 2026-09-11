import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

// BLOCKING 3: Task 7 deleted Layout.tsx, the only thing that ever rendered
// LogPanel — the run-artifact viewer (server/workspace.py's per-run .md files,
// token usage) became unreachable even though both sides still implement it.
// Separately, a finished run's answer (runResult) was never rendered anywhere.
// Ruling: render both, don't delete the now-dead wiring.
describe('Dashboard — LogPanel mounted and run result visible', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    useExecutionStore.getState().reset()
  })

  it('mounts LogPanel (Log/Files tabs visible)', () => {
    renderDashboard()
    expect(screen.getByRole('button', { name: /Log/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Files/i })).toBeInTheDocument()
  })

  it('shows a completed run\'s final answer', () => {
    useExecutionStore.setState({
      runStatus: 'complete',
      runResult: { answer: 'the final answer text', reviewDelta: null, reviewBranch: null },
    })
    renderDashboard()
    expect(screen.getByText(/the final answer text/)).toBeInTheDocument()
  })
})
