import { beforeEach, describe, expect, it } from 'vitest'
import { type Architecture, ArchitectureSchema } from '@/types'
import { useGraphStore } from '@/stores/useGraphStore'

const architecture: Architecture = {
  version: '0.1',
  metadata: {
    name: 'round-trip',
    description: 'Graph store serialization regression fixture.',
    createdAt: '2026-08-04T00:00:00.000Z',
  },
  nodes: [
    {
      id: 'planning',
      type: 'planning.decompose',
      position: { x: 120, y: 80 },
      config: { strategy: 'goal', modelSlots: [{ id: 'plan-model', model: 'test-model' }] },
    },
    {
      id: 'review',
      type: 'review.intent',
      position: { x: 420, y: 240 },
      config: { criteria: ['answer is complete'], maxRetries: 3 },
    },
  ],
  edges: [
    {
      id: 'planning-to-review',
      source: 'planning',
      sourceHandle: 'plan',
      target: 'review',
      targetHandle: 'answer',
    },
  ],
  loopPolicies: [
    {
      id: 'loop-1',
      kind: 'critiqueRevise' as const,
      feedbackEdgeIds: ['planning-to-review'],
      memberNodeIds: ['planning', 'review'],
      exitEdgeIds: ['planning-to-review'],
      guard: { maxIterations: 3 },
      onExhaustion: 'exit' as const,
    },
  ],
}

describe('useGraphStore architecture serialization', () => {
  beforeEach(() => {
    useGraphStore.getState().loadArchitecture(ArchitectureSchema.parse(architecture))
  })

  it('preserves node identities, types, positions, and config through load and serialize', () => {
    const result = useGraphStore.getState().toArchitecture('serialized')

    expect(result.nodes).toEqual(architecture.nodes)
  })

  it('preserves edge identities, endpoints, and port handles through load and serialize', () => {
    const result = useGraphStore.getState().toArchitecture('serialized')

    expect(result.edges).toEqual(architecture.edges)
  })

  it('preserves loop policies through load and serialize', () => {
    const result = useGraphStore.getState().toArchitecture('serialized')

    expect(result.loopPolicies).toEqual(architecture.loopPolicies)
  })

  it('restores positions from before the latest layout without changing topology', () => {
    const previous = architecture.nodes.map((node) => node.position)

    useGraphStore.getState().applyNodePositions({
      planning: { x: 0, y: 0 },
      review: { x: 300, y: 0 },
    })
    useGraphStore.getState().undoLastLayout()

    expect(useGraphStore.getState().nodes.map((node) => node.position)).toEqual(previous)
    expect(useGraphStore.getState().toArchitecture('serialized').edges).toEqual(architecture.edges)
  })

  it('records which node Arrange radially was centered on', () => {
    useGraphStore.getState().applyNodePositions(
      { planning: { x: 0, y: 0 }, review: { x: 300, y: 0 } },
      'planning',
    )

    expect(useGraphStore.getState().radialCenterId).toBe('planning')
  })

  it('leaves the radial center untouched when applyNodePositions is called without one', () => {
    useGraphStore.getState().applyNodePositions(
      { planning: { x: 0, y: 0 }, review: { x: 300, y: 0 } },
      'planning',
    )
    useGraphStore.getState().applyNodePositions({ planning: { x: 10, y: 10 } })

    expect(useGraphStore.getState().radialCenterId).toBe('planning')
  })

  it('clears the radial center on undo — pre-arrange positions have no meaningful center', () => {
    useGraphStore.getState().applyNodePositions(
      { planning: { x: 0, y: 0 }, review: { x: 300, y: 0 } },
      'planning',
    )
    useGraphStore.getState().undoLastLayout()

    expect(useGraphStore.getState().radialCenterId).toBeNull()
  })

  it('clears the radial center when a new architecture is loaded', () => {
    useGraphStore.getState().applyNodePositions({ planning: { x: 0, y: 0 } }, 'planning')
    useGraphStore.getState().loadArchitecture(ArchitectureSchema.parse(architecture))

    expect(useGraphStore.getState().radialCenterId).toBeNull()
  })
})
