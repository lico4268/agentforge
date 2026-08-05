import { describe, expect, it } from 'vitest'
import { buildLoopScopeInspectorModel } from '@/canvas/loops/loopScopeInspector'
import type { LoopScope } from '@/canvas/loops/loopScopes'

const scope: LoopScope = {
  id: 'loop:1:a,b',
  tier: 1,
  memberNodeIds: ['a', 'b'],
  feedbackEdgeIds: ['ab', 'ba'],
  entryEdgeIds: ['in'],
  exitEdgeIds: ['out'],
  reentryNodeIds: ['a', 'b'],
}

describe('buildLoopScopeInspectorModel', () => {
  it('projects transitions and aggregates member runtime without inventing iterations', () => {
    const model = buildLoopScopeInspectorModel(
      scope,
      [
        { id: 'in', source: 'start', target: 'a', sourceHandle: 'out' },
        { id: 'ab', source: 'a', target: 'b', sourceHandle: 'refine' },
        { id: 'ba', source: 'b', target: 'a', sourceHandle: 'revise' },
        { id: 'out', source: 'b', target: 'end', sourceHandle: 'accept' },
      ],
      {
        a: { status: 'success', callCount: 2, totalDurationMs: 40, totalTokens: 11 },
        b: { status: 'running', callCount: 1, totalDurationMs: 10, totalTokens: 7 },
      },
      true,
    )

    expect(model.transitions.map((transition) => [transition.kind, transition.id])).toEqual([
      ['entry', 'in'],
      ['trigger', 'ab'],
      ['trigger', 'ba'],
      ['exit', 'out'],
    ])
    expect(model.collapsed).toBe(true)
    expect(model.guardStatus).toBe('custom-policy')
    expect(model.runtime).toEqual({ status: 'running', calls: 3, durationMs: 50, tokens: 18 })
  })

  it('prioritizes a failed member in the aggregate status', () => {
    const model = buildLoopScopeInspectorModel(scope, [], {
      a: { status: 'running', callCount: 1, totalDurationMs: 0, totalTokens: 0 },
      b: { status: 'failed', callCount: 0, totalDurationMs: 0, totalTokens: 0 },
    }, false)

    expect(model.runtime.status).toBe('failed')
    expect(model.collapsed).toBe(false)
  })

  it('reports an absent exit route as not configured', () => {
    const model = buildLoopScopeInspectorModel({ ...scope, exitEdgeIds: [] }, [], {}, true)

    expect(model.guardStatus).toBe('not-configured')
  })
})
