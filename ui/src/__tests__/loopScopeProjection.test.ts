import { describe, expect, it } from 'vitest'
import { projectLoopScopes } from '@/canvas/loops/loopScopeProjection'
import type { LoopScope } from '@/canvas/loops/loopScopes'

type N = { id: string; position: { x: number; y: number } }
type E = { id: string; source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }

const makeContainer = (scope: LoopScope, position: { x: number; y: number }): N => ({
  id: scope.id,
  position,
})

const tier1Scope: LoopScope = {
  id: 'loop:1:a,b',
  tier: 1,
  memberNodeIds: ['a', 'b'],
  feedbackEdgeIds: ['forward', 'refine'],
  entryEdgeIds: ['entry'],
  exitEdgeIds: ['exit'],
  reentryNodeIds: ['a', 'b'],
}

function fixture() {
  const nodes: N[] = [
    { id: 'start', position: { x: 0, y: 0 } },
    { id: 'a', position: { x: 100, y: 0 } },
    { id: 'b', position: { x: 200, y: 0 } },
    { id: 'end', position: { x: 300, y: 0 } },
  ]
  const edges: E[] = [
    { id: 'entry', source: 'start', target: 'a' },
    { id: 'forward', source: 'a', target: 'b' },
    { id: 'refine', source: 'b', target: 'a' },
    { id: 'exit', source: 'b', target: 'end' },
  ]
  return { nodes, edges }
}

describe('projectLoopScopes', () => {
  it('passes nodes/edges through unchanged when there are no loop scopes', () => {
    const { nodes, edges } = fixture()
    const result = projectLoopScopes(nodes, edges, [], new Set(), makeContainer)
    expect(result.nodes).toEqual(nodes)
    expect(result.edges).toEqual(edges)
    expect(result.reentryNodeIds.size).toBe(0)
  })

  it('collapses a tier-1 scope by default: hides members, drops internal edges, reroutes entry/exit', () => {
    const { nodes, edges } = fixture()
    const result = projectLoopScopes(nodes, edges, [tier1Scope], new Set(), makeContainer)

    const nodeIds = result.nodes.map((n) => n.id).sort()
    expect(nodeIds).toEqual(['end', 'loop:1:a,b', 'start'])

    const container = result.nodes.find((n) => n.id === 'loop:1:a,b')!
    // centroid of a(100,0) and b(200,0) => (150, 0)
    expect(container.position).toEqual({ x: 150, y: 0 })

    const edgeIds = result.edges.map((e) => e.id).sort()
    expect(edgeIds).toEqual(['entry', 'exit']) // forward/refine (internal) dropped

    const entry = result.edges.find((e) => e.id === 'entry')!
    expect(entry.source).toBe('start')
    expect(entry.target).toBe('loop:1:a,b')
    expect(entry.targetHandle).toBe('entry')

    const exit = result.edges.find((e) => e.id === 'exit')!
    expect(exit.source).toBe('loop:1:a,b')
    expect(exit.target).toBe('end')
    expect(exit.sourceHandle).toBe('exit')
  })

  it('leaves a scope expanded (members + internal edges visible) when its id is in expandedScopeIds', () => {
    const { nodes, edges } = fixture()
    const result = projectLoopScopes(nodes, edges, [tier1Scope], new Set([tier1Scope.id]), makeContainer)

    const nodeIds = result.nodes.map((n) => n.id).sort()
    expect(nodeIds).toEqual(['a', 'b', 'end', 'start'])
    expect(result.edges).toEqual(edges)
    expect([...result.reentryNodeIds].sort()).toEqual(['a', 'b'])
    expect(result.collapseAffordanceNodeIdByScopeId[tier1Scope.id]).toBe('a')
  })

  it('reroutes both ends of an edge directly linking two different collapsed scopes', () => {
    const nodes: N[] = [
      { id: 'a', position: { x: 0, y: 0 } },
      { id: 'b', position: { x: 100, y: 0 } },
      { id: 'c', position: { x: 200, y: 0 } },
      { id: 'd', position: { x: 300, y: 0 } },
    ]
    const edges: E[] = [
      { id: 'ab', source: 'a', target: 'b' },
      { id: 'ba', source: 'b', target: 'a' },
      { id: 'bridge', source: 'b', target: 'c' },
      { id: 'cd', source: 'c', target: 'd' },
      { id: 'dc', source: 'd', target: 'c' },
    ]
    const scopeAB: LoopScope = {
      id: 'loop:1:a,b',
      tier: 1,
      memberNodeIds: ['a', 'b'],
      feedbackEdgeIds: ['ab', 'ba'],
      entryEdgeIds: [],
      exitEdgeIds: ['bridge'],
      reentryNodeIds: ['a', 'b'],
    }
    const scopeCD: LoopScope = {
      id: 'loop:1:c,d',
      tier: 1,
      memberNodeIds: ['c', 'd'],
      feedbackEdgeIds: ['cd', 'dc'],
      entryEdgeIds: ['bridge'],
      exitEdgeIds: [],
      reentryNodeIds: ['c', 'd'],
    }

    const result = projectLoopScopes(nodes, edges, [scopeAB, scopeCD], new Set(), makeContainer)

    expect(result.edges).toHaveLength(1)
    const bridge = result.edges[0]
    expect(bridge.id).toBe('bridge')
    expect(bridge.source).toBe('loop:1:a,b')
    expect(bridge.sourceHandle).toBe('bridge')
    expect(bridge.target).toBe('loop:1:c,d')
    expect(bridge.targetHandle).toBe('bridge')
  })
})
