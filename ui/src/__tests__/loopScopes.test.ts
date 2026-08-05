import { describe, expect, it } from 'vitest'
import { buildLoopScopes } from '@/canvas/loops/loopScopes'

type E = { id: string; source: string; target: string }

describe('buildLoopScopes', () => {
  it('returns no scopes when there are no cycles', () => {
    const edges: E[] = [{ id: 'e1', source: 'a', target: 'b' }]
    expect(buildLoopScopes(['a', 'b'], edges)).toEqual([])
  })

  it('builds a tier-1 scope for a 2-member cycle with entry/exit/reentry edges', () => {
    const edges: E[] = [
      { id: 'entry', source: 'start', target: 'a' },
      { id: 'forward', source: 'a', target: 'b' },
      { id: 'refine', source: 'b', target: 'a' },
      { id: 'exit', source: 'b', target: 'end' },
    ]
    const scopes = buildLoopScopes(['start', 'a', 'b', 'end'], edges)

    expect(scopes).toHaveLength(1)
    expect(scopes[0].tier).toBe(1)
    expect([...scopes[0].memberNodeIds].sort()).toEqual(['a', 'b'])
    expect([...scopes[0].feedbackEdgeIds].sort()).toEqual(['forward', 'refine'])
    expect(scopes[0].entryEdgeIds).toEqual(['entry'])
    expect(scopes[0].exitEdgeIds).toEqual(['exit'])
    // both members are targeted by an internal edge (a<-refine, b<-forward) — both re-enter
    expect([...scopes[0].reentryNodeIds].sort()).toEqual(['a', 'b'])
  })

  it('gives the same scope the same id across calls (stable, order-independent)', () => {
    const edgesA: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'a' },
    ]
    const edgesB: E[] = [
      { id: 'e2', source: 'b', target: 'a' },
      { id: 'e1', source: 'a', target: 'b' },
    ]
    const idA = buildLoopScopes(['a', 'b'], edgesA)[0].id
    const idB = buildLoopScopes(['b', 'a'], edgesB)[0].id
    expect(idA).toBe(idB)
  })

  it('excludes tier-3 (overlapping cycle) candidates — those stay edge-level, not a LoopScope', () => {
    // a<->b and b<->c share node b: two simple cycles, one SCC → tier 3
    const edges: E[] = [
      { id: 'ab', source: 'a', target: 'b' },
      { id: 'ba', source: 'b', target: 'a' },
      { id: 'bc', source: 'b', target: 'c' },
      { id: 'cb', source: 'c', target: 'b' },
    ]
    const scopes = buildLoopScopes(['a', 'b', 'c'], edges)
    expect(scopes).toEqual([])
  })

  it('builds a tier-2 scope for a 3-member cycle', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
      { id: 'e3', source: 'c', target: 'a' },
    ]
    const scopes = buildLoopScopes(['a', 'b', 'c'], edges)
    expect(scopes).toHaveLength(1)
    expect(scopes[0].tier).toBe(2)
    expect([...scopes[0].memberNodeIds].sort()).toEqual(['a', 'b', 'c'])
  })
})
