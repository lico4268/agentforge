import { describe, expect, it } from 'vitest'
import { findTier3FeedbackEdgeIds } from '@/canvas/loops/loopEdgeAnnotations'

describe('findTier3FeedbackEdgeIds', () => {
  it('marks every internal edge in an overlapping-cycle candidate', () => {
    const edges = [
      { id: 'ab', source: 'a', target: 'b' },
      { id: 'ba', source: 'b', target: 'a' },
      { id: 'bc', source: 'b', target: 'c' },
      { id: 'cb', source: 'c', target: 'b' },
      { id: 'out', source: 'c', target: 'd' },
    ]

    expect(findTier3FeedbackEdgeIds(['a', 'b', 'c', 'd'], edges)).toEqual(
      new Set(['ab', 'ba', 'bc', 'cb']),
    )
  })

  it('does not annotate a collapsible Tier 1 loop', () => {
    expect(findTier3FeedbackEdgeIds(['a', 'b'], [
      { id: 'ab', source: 'a', target: 'b' },
      { id: 'ba', source: 'b', target: 'a' },
    ])).toEqual(new Set())
  })
})
