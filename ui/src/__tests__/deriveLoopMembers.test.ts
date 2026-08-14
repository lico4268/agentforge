import { describe, expect, it } from 'vitest'
import { deriveLoopMembers } from '@/canvas/loop/deriveLoopMembers'

// Mirrors STARTER_ARCHITECTURE (ui/src/app/starterArchitecture.ts): a single
// review→loop_guard→reasoning cycle plus two exits (accept, clarify) that
// must NOT be pulled into the loop's member set.
const nodeIds = ['input', 'planning', 'reasoning', 'review', 'loop_guard', 'human_checkpoint', 'output']
const edges = [
  { id: 'e1', source: 'input', sourceHandle: 'task', target: 'planning' },
  { id: 'e2', source: 'planning', sourceHandle: 'plan', target: 'reasoning' },
  { id: 'e3', source: 'input', sourceHandle: 'task', target: 'reasoning' },
  { id: 'e4', source: 'reasoning', sourceHandle: 'answer', target: 'review' },
  { id: 'e5', source: 'review', sourceHandle: 'accept', target: 'output' },
  { id: 'e6', source: 'review', sourceHandle: 'refine', target: 'loop_guard' },
  { id: 'e7', source: 'review', sourceHandle: 'clarify', target: 'human_checkpoint' },
  { id: 'e8', source: 'human_checkpoint', sourceHandle: 'approve', target: 'output' },
  { id: 'e9', source: 'loop_guard', sourceHandle: 'loopBack', target: 'reasoning' },
  { id: 'e10', source: 'loop_guard', sourceHandle: 'exit', target: 'output' },
]

describe('deriveLoopMembers', () => {
  it('returns exactly the nodes on the cycle back to the guard, excluding both exits and the guard itself', () => {
    expect(deriveLoopMembers(nodeIds, edges, 'loop_guard')).toEqual(['reasoning', 'review'])
  })

  it('returns an empty array when the guard has no loopBack edge wired yet', () => {
    const noLoopBack = edges.filter((e) => e.sourceHandle !== 'loopBack')
    expect(deriveLoopMembers(nodeIds, noLoopBack, 'loop_guard')).toEqual([])
  })

  it('returns an empty array for a node id that is not a loop.guard at all', () => {
    expect(deriveLoopMembers(nodeIds, edges, 'review')).toEqual([])
  })
})
