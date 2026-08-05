import { describe, expect, it } from 'vitest'
import { findLoopCandidates, findStronglyConnectedComponents } from '@/canvas/loops/loopCandidates'

type E = { id: string; source: string; target: string }

const sortedIds = (ids: string[]) => [...ids].sort()

describe('findStronglyConnectedComponents', () => {
  it('puts each node in its own component when there are no edges', () => {
    const sccs = findStronglyConnectedComponents(['a', 'b', 'c'], [])
    const sorted = sccs.map((c) => sortedIds(c)).sort()

    expect(sorted).toEqual([['a'], ['b'], ['c']])
  })

  it('does not merge nodes connected only by a one-way chain', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
    ]
    const sccs = findStronglyConnectedComponents(['a', 'b', 'c'], edges)
    const sorted = sccs.map((c) => sortedIds(c)).sort()

    expect(sorted).toEqual([['a'], ['b'], ['c']])
  })

  it('merges a simple 2-cycle into one component', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'a' },
    ]
    const sccs = findStronglyConnectedComponents(['a', 'b'], edges)

    expect(sccs).toHaveLength(1)
    expect(sortedIds(sccs[0])).toEqual(['a', 'b'])
  })

  it('keeps a self-loop as its own size-1 component', () => {
    const edges: E[] = [{ id: 'e1', source: 'a', target: 'a' }]
    const sccs = findStronglyConnectedComponents(['a'], edges)

    expect(sccs).toEqual([['a']])
  })

  it('merges two cycles that share a node into a single component', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'a' },
      { id: 'e3', source: 'a', target: 'c' },
      { id: 'e4', source: 'c', target: 'a' },
    ]
    const sccs = findStronglyConnectedComponents(['a', 'b', 'c'], edges)

    expect(sccs).toHaveLength(1)
    expect(sortedIds(sccs[0])).toEqual(['a', 'b', 'c'])
  })
})

describe('findLoopCandidates', () => {
  it('reports no candidates for an acyclic graph', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
    ]
    const { loops, selfLoops } = findLoopCandidates(['a', 'b', 'c'], edges)

    expect(loops).toEqual([])
    expect(selfLoops).toEqual([])
  })

  it('reports a self-loop separately, not as a Tier 1/2/3 loop', () => {
    const edges: E[] = [{ id: 'e1', source: 'a', target: 'a' }]
    const { loops, selfLoops } = findLoopCandidates(['a'], edges)

    expect(loops).toEqual([])
    expect(selfLoops).toEqual([{ nodeId: 'a', edgeId: 'e1' }])
  })

  it('classifies a 2-member single cycle as Tier 1', () => {
    const edges: E[] = [
      { id: 'e1', source: 'reasoning', target: 'review' },
      { id: 'e2', source: 'review', target: 'reasoning' },
    ]
    const { loops } = findLoopCandidates(['reasoning', 'review'], edges)

    expect(loops).toHaveLength(1)
    expect(loops[0].tier).toBe(1)
    expect(sortedIds(loops[0].memberNodeIds)).toEqual(['reasoning', 'review'])
    expect(sortedIds(loops[0].feedbackEdgeIds)).toEqual(['e1', 'e2'])
  })

  it('classifies a 3-member single cycle as Tier 2', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
      { id: 'e3', source: 'c', target: 'a' },
    ]
    const { loops } = findLoopCandidates(['a', 'b', 'c'], edges)

    expect(loops).toHaveLength(1)
    expect(loops[0].tier).toBe(2)
    expect(sortedIds(loops[0].memberNodeIds)).toEqual(['a', 'b', 'c'])
  })

  it('classifies two cycles sharing a node as Tier 3, not Tier 2', () => {
    // Review participates in both a refine loop with Reasoning and a revise
    // loop with Human Checkpoint — exactly the case that broke the SCC-size
    // heuristic during design review.
    const edges: E[] = [
      { id: 'refine-out', source: 'review', target: 'reasoning' },
      { id: 'refine-in', source: 'reasoning', target: 'review' },
      { id: 'revise-out', source: 'review', target: 'human' },
      { id: 'revise-in', source: 'human', target: 'review' },
    ]
    const { loops } = findLoopCandidates(['reasoning', 'review', 'human'], edges)

    expect(loops).toHaveLength(1)
    expect(loops[0].tier).toBe(3)
    expect(sortedIds(loops[0].memberNodeIds)).toEqual(['human', 'reasoning', 'review'])
  })

  it('reports two disjoint cycles as two separate Tier 1 candidates', () => {
    const edges: E[] = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'a' },
      { id: 'e3', source: 'c', target: 'd' },
      { id: 'e4', source: 'd', target: 'c' },
    ]
    const { loops } = findLoopCandidates(['a', 'b', 'c', 'd'], edges)

    expect(loops).toHaveLength(2)
    expect(loops.map((l) => l.tier)).toEqual([1, 1])
    const memberSets = loops.map((l) => sortedIds(l.memberNodeIds)).sort()
    expect(memberSets).toEqual([
      ['a', 'b'],
      ['c', 'd'],
    ])
  })

  it('stays fast on a large single ring (exactly one simple cycle, no chords)', () => {
    const n = 60
    const ids = Array.from({ length: n }, (_, i) => `n${i}`)
    const edges: E[] = ids.map((id, i) => ({
      id: `e${i}`,
      source: id,
      target: ids[(i + 1) % n],
    }))

    const start = performance.now()
    const { loops } = findLoopCandidates(ids, edges)
    const elapsedMs = performance.now() - start

    expect(loops).toHaveLength(1)
    expect(loops[0].tier).toBe(2)
    expect(elapsedMs).toBeLessThan(500)
  })

  it('stays fast on a densely cross-linked SCC with many simple cycles (early exit)', () => {
    const n = 10
    const ids = Array.from({ length: n }, (_, i) => `n${i}`)
    const edges: E[] = []
    let seq = 0
    for (const a of ids) {
      for (const b of ids) {
        if (a !== b) edges.push({ id: `e${seq++}`, source: a, target: b })
      }
    }

    const start = performance.now()
    const { loops } = findLoopCandidates(ids, edges)
    const elapsedMs = performance.now() - start

    expect(loops).toHaveLength(1)
    expect(loops[0].tier).toBe(3)
    expect(elapsedMs).toBeLessThan(500)
  })
})
