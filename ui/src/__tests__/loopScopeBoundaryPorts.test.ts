import { describe, expect, it } from 'vitest'
import { computeBoundaryPortAngles } from '@/canvas/loops/loopScopeBoundaryPorts'

describe('computeBoundaryPortAngles', () => {
  const containerCenter = { x: 0, y: 0 }

  it('points an entry port toward its external source, on the real screen direction', () => {
    const centerPointById = new Map([['upstream', { x: -100, y: 0 }]])
    const ports = computeBoundaryPortAngles(
      containerCenter,
      { entryEdgeIds: ['e1'], exitEdgeIds: [] },
      [{ id: 'e1', source: 'upstream', target: 'container' }],
      centerPointById,
    )

    expect(ports).toEqual([{ edgeId: 'e1', isInput: true, angleDeg: 180 }])
  })

  it('points an exit port toward its external target', () => {
    const centerPointById = new Map([['downstream', { x: 100, y: 0 }]])
    const ports = computeBoundaryPortAngles(
      containerCenter,
      { entryEdgeIds: [], exitEdgeIds: ['e2'] },
      [{ id: 'e2', source: 'container', target: 'downstream' }],
      centerPointById,
    )

    expect(ports).toEqual([{ edgeId: 'e2', isInput: false, angleDeg: 0 }])
  })

  it('skips a boundary edge whose partner position is unknown', () => {
    const ports = computeBoundaryPortAngles(
      containerCenter,
      { entryEdgeIds: ['missing'], exitEdgeIds: [] },
      [{ id: 'missing', source: 'ghost', target: 'container' }],
      new Map(),
    )

    expect(ports).toEqual([])
  })
})
