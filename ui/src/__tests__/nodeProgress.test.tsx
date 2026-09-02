import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NodeProgress } from '@/app/NodeProgress'

describe('NodeProgress', () => {
  it('numbers repeat visits of the same node', () => {
    render(
      <NodeProgress
        entries={[
          { nodeId: 'reasoning', status: 'done', durationMs: 1200, output: null },
          { nodeId: 'review', status: 'done', durationMs: 800, output: null },
          { nodeId: 'reasoning', status: 'running', durationMs: null, output: null },
        ]}
        onResume={() => {}}
      />,
    )
    expect(screen.getByText('reasoning #1')).toBeInTheDocument()
    expect(screen.getByText('reasoning #2')).toBeInTheDocument()
    expect(screen.getByText('review')).toBeInTheDocument()
  })

  it('shows checkpoint buttons only for a paused checkpoint entry', () => {
    render(
      <NodeProgress
        entries={[
          { nodeId: '승인', status: 'paused', durationMs: null, output: null },
          { nodeId: 'reasoning', status: 'done', durationMs: 10, output: null },
        ]}
        onResume={() => {}}
      />,
    )
    expect(screen.getAllByRole('button', { name: /approve/i })).toHaveLength(1)
  })
})
