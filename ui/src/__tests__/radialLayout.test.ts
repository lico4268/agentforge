import { describe, expect, it } from 'vitest'
import { radialLayout } from '@/canvas/layout/radialLayout'

const nodes = [
  { id: 'center', position: { x: 400, y: 400 } },
  { id: 'a', position: { x: 0, y: 0 } },
  { id: 'b', position: { x: 100, y: 0 } },
  { id: 'isolated', position: { x: 900, y: 900 } },
]

describe('radialLayout', () => {
  it('keeps the center position and places connected neighbors on the first ring', () => {
    const positions = radialLayout(nodes, [
      { id: 'center-a', source: 'center', target: 'a' },
      { id: 'center-b', source: 'center', target: 'b' },
    ], { centerId: 'center' })

    expect(positions.center).toEqual({ x: 400, y: 400 })
    expect(positions.a).not.toEqual(nodes[1].position)
    expect(positions.b).not.toEqual(nodes[2].position)
    expect(positions.isolated).toBeDefined()
  })

  it('returns deterministic coordinates for identical graph input', () => {
    const edges = [{ id: 'center-a', source: 'center', target: 'a' }]

    expect(radialLayout(nodes, edges, { centerId: 'center' })).toEqual(
      radialLayout(nodes, edges, { centerId: 'center' }),
    )
  })
})

describe('radialLayout with per-node diameter (collapsed loop units)', () => {
  const angleDiff = (a: number, b: number) => {
    let diff = Math.abs(a - b)
    if (diff > Math.PI) diff = 2 * Math.PI - diff
    return diff
  }

  it('gives a larger declared diameter more angular room, shrinking the gap between its smaller neighbors', () => {
    const ringNodes = [
      { id: 'center', position: { x: 0, y: 0 } },
      { id: 'big', position: { x: 0, y: 0 } },
      { id: 's1', position: { x: 0, y: 0 } },
      { id: 's2', position: { x: 0, y: 0 } },
    ]
    const edges = [
      { id: 'e-big', source: 'center', target: 'big' },
      { id: 'e-s1', source: 'center', target: 's1' },
      { id: 'e-s2', source: 'center', target: 's2' },
    ]
    const getNodeDiameter = (id: string) => (id === 'big' ? 300 : 112)

    const positions = radialLayout(ringNodes, edges, { centerId: 'center', getNodeDiameter })
    const center = { x: positions.center.x + 56, y: positions.center.y + 56 }
    const angleOf = (id: string) => {
      const p = positions[id]
      const diameter = getNodeDiameter(id)
      return Math.atan2(p.y + diameter / 2 - center.y, p.x + diameter / 2 - center.x)
    }

    const gapSmallToSmall = angleDiff(angleOf('s1'), angleOf('s2'))
    const gapBigToS1 = angleDiff(angleOf('big'), angleOf('s1'))

    // uniform placement would put every pair 120 degrees apart; the big node
    // should claim extra arc from its neighbors, shrinking the small-small gap
    // and widening the big-small gap.
    expect(gapSmallToSmall).toBeLessThan((2 * Math.PI) / 3)
    expect(gapBigToS1).toBeGreaterThan((2 * Math.PI) / 3)
  })

  it('pushes an outer ring further out when the inner ring has a larger declared diameter', () => {
    const chainNodes = [
      { id: 'center', position: { x: 0, y: 0 } },
      { id: 'a', position: { x: 0, y: 0 } },
      { id: 'b', position: { x: 0, y: 0 } },
    ]
    const edges = [
      { id: 'e1', source: 'center', target: 'a' },
      { id: 'e2', source: 'a', target: 'b' },
    ]

    const distanceFromCenter = (
      positions: Record<string, { x: number; y: number }>,
      id: string,
      diameter: number,
    ) => {
      const center = { x: positions.center.x + 56, y: positions.center.y + 56 }
      const p = positions[id]
      return Math.hypot(p.x + diameter / 2 - center.x, p.y + diameter / 2 - center.y)
    }

    const baseline = radialLayout(chainNodes, edges, { centerId: 'center' })
    const withBigInnerRing = radialLayout(chainNodes, edges, {
      centerId: 'center',
      getNodeDiameter: (id) => (id === 'a' ? 400 : 112),
    })

    expect(distanceFromCenter(withBigInnerRing, 'b', 112)).toBeGreaterThan(
      distanceFromCenter(baseline, 'b', 112),
    )
  })
})
