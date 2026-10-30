import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LogPanel } from '@/panels/LogPanel'

// Smoke test: with no events in the store, renders the empty-state message.
describe('LogPanel', () => {
  it('shows the guidance text when there are no events', () => {
    render(<LogPanel />)
    expect(screen.getByText(/No events yet/i)).toBeInTheDocument()
    // The Log tab is the default active tab
    expect(screen.getByRole('button', { name: /Log/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Files/i })).toBeInTheDocument()
  })
})