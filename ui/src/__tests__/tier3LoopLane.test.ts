import { describe, expect, it } from 'vitest'
import { computeTier3LoopLane, tier3LoopLaneRoute } from '@/canvas/loops/tier3LoopLane'

describe('computeTier3LoopLane', () => {
  it('uses the arranged center and places the annulus outside the outermost node', () => {
    const lane = computeTier3LoopLane([
      { id: 'hub', position: { x: 0, y: 0 } },
      { id: 'outer', position: { x: 300, y: 0 } },
    ], 'hub')

    expect(lane).toEqual({ center: { x: 56, y: 56 }, outerRadius: 444 })
  })

  it('recomputes from the node centroid before the graph has been arranged', () => {
    const lane = computeTier3LoopLane([
      { id: 'a', position: { x: 0, y: 0 } },
      { id: 'b', position: { x: 200, y: 0 } },
    ], null)

    expect(lane?.center).toEqual({ x: 156, y: 56 })
    expect(lane?.outerRadius).toBe(244)
  })
})

describe('tier3LoopLaneRoute', () => {
  it('routes through the outer annulus and anchors the label on its arc', () => {
    const route = tier3LoopLaneRoute(
      { x: 56, y: 56 },
      { x: 356, y: 56 },
      { center: { x: 206, y: 56 }, outerRadius: 294 },
      14,
    )

    expect(route.path).toContain('A 308 308')
    expect(route.path).toContain('M 56 56')
    expect(route.path).toContain('L 356 56')
    expect(route.labelY).not.toBe(56)
  })
})
