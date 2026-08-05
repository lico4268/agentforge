import { describe, expect, it } from 'vitest'
import {
  buildLoopAnchorsByNodeId,
  buildLoopCandidateViews,
  candidateReturnEdgeIds,
} from '@/canvas/loops/loopAnchors'

const nodes = ['reasoning', 'review']

describe('loop anchor presentation', () => {
  it('creates a stable candidate label and paired anchors for a named return edge', () => {
    const edges = [
      { id: 'forward', source: 'reasoning', target: 'review', sourceHandle: 'draft' },
      { id: 'refine', source: 'review', target: 'reasoning', sourceHandle: 'refine' },
    ]

    const candidates = buildLoopCandidateViews(nodes, edges)
    const anchorsByNodeId = buildLoopAnchorsByNodeId(candidates, edges)

    expect(candidates).toMatchObject([{
      id: 'loop:1:reasoning,review',
      label: 'L1',
      returnEdgeIds: ['refine'],
    }])
    expect(anchorsByNodeId.get('review')).toEqual([{
      candidateId: 'loop:1:reasoning,review',
      label: 'L1',
      role: 'feedbackSource',
    }])
    expect(anchorsByNodeId.get('reasoning')).toEqual([{
      candidateId: 'loop:1:reasoning,review',
      label: 'L1',
      role: 'reentryTarget',
    }])
    expect(candidateReturnEdgeIds(candidates)).toEqual(new Set(['refine']))
  })

  it('keeps unknown cycle edges visible while still exposing candidate anchors', () => {
    const edges = [
      { id: 'ab', source: 'reasoning', target: 'review', sourceHandle: 'out' },
      { id: 'ba', source: 'review', target: 'reasoning', sourceHandle: 'out' },
    ]

    const candidates = buildLoopCandidateViews(nodes, edges)
    const anchorsByNodeId = buildLoopAnchorsByNodeId(candidates, edges)

    expect(candidates[0].returnEdgeIds).toEqual([])
    expect(candidateReturnEdgeIds(candidates)).toEqual(new Set())
    expect(anchorsByNodeId.get('reasoning')).toHaveLength(2)
    expect(anchorsByNodeId.get('review')).toHaveLength(2)
  })
})
