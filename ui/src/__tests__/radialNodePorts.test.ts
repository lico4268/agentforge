import { Position } from '@xyflow/react'
import { describe, expect, it } from 'vitest'
import {
  angleDegBetween,
  clusterFallbackAngles,
  connectedHandleStyle,
  labelPointFromAngleDeg,
  pointFromAngleDeg,
  positionFromAngleDeg,
  resolveNodePortAngles,
  revealableHandleStyle,
  unconnectedPortAngles,
} from '@/canvas/nodes/radialPortGeometry'

describe('positionFromAngleDeg', () => {
  it('buckets the four cardinal angles to their matching Position', () => {
    expect(positionFromAngleDeg(0)).toBe(Position.Right)
    expect(positionFromAngleDeg(90)).toBe(Position.Top)
    expect(positionFromAngleDeg(180)).toBe(Position.Left)
    expect(positionFromAngleDeg(-90)).toBe(Position.Bottom)
  })

  it('switches bucket exactly at the 45 degree boundary', () => {
    expect(positionFromAngleDeg(45)).toBe(Position.Right)
    expect(positionFromAngleDeg(46)).toBe(Position.Top)
  })

  it('normalizes angles outside (-180, 180] before bucketing', () => {
    expect(positionFromAngleDeg(360)).toBe(Position.Right)
    expect(positionFromAngleDeg(-270)).toBe(Position.Top)
    expect(positionFromAngleDeg(540)).toBe(Position.Left)
  })
})

describe('angleDegBetween', () => {
  it('returns 0 when the target is directly to the right', () => {
    expect(angleDegBetween({ x: 0, y: 0 }, { x: 100, y: 0 })).toBeCloseTo(0)
  })

  it('returns 90 when the target is directly above on screen (smaller y)', () => {
    expect(angleDegBetween({ x: 0, y: 0 }, { x: 0, y: -100 })).toBeCloseTo(90)
  })

  it('returns -90 when the target is directly below on screen (larger y)', () => {
    expect(angleDegBetween({ x: 0, y: 0 }, { x: 0, y: 100 })).toBeCloseTo(-90)
  })

  it('returns 180 when the target is directly to the left', () => {
    expect(angleDegBetween({ x: 0, y: 0 }, { x: -100, y: 0 })).toBeCloseTo(180)
  })

  it('agrees with pointFromAngleDeg\'s convention: the angle it returns reproduces the same point', () => {
    const from = { x: 0, y: 0 }
    const to = { x: 30, y: -70 }
    const angle = angleDegBetween(from, to)

    // a point placed exactly at that angle should sit on the ray from the
    // node center toward `to`.
    const point = pointFromAngleDeg(angle)
    const radians = (angle * Math.PI) / 180
    expect(point.left).toBeCloseTo(56 + 56 * Math.cos(radians))
    expect(point.top).toBeCloseTo(56 - 56 * Math.sin(radians))
  })
})

describe('resolveNodePortAngles', () => {
  it('spreads ports evenly around the full circle when none have a partner angle', () => {
    const angles = resolveNodePortAngles([{}, {}, {}, {}])
    const sorted = [...angles].sort((a, b) => a - b)

    // 4 ports around a full circle -> 90deg apart, wherever the seam falls
    for (let i = 1; i < sorted.length; i += 1) {
      expect(sorted[i] - sorted[i - 1]).toBeCloseTo(90)
    }
  })

  it('places a single port exactly on its real partner angle, anywhere on the circle', () => {
    // the resolved angle may come back as an equivalent representative
    // (e.g. -150 vs 210) since both denote the same physical direction —
    // compare the rendered point, not the raw degree value.
    const [resolved] = resolveNodePortAngles([{ partnerAngleDeg: -150 }])
    expect(pointFromAngleDeg(resolved).left).toBeCloseTo(pointFromAngleDeg(-150).left)
    expect(pointFromAngleDeg(resolved).top).toBeCloseTo(pointFromAngleDeg(-150).top)

    expect(resolveNodePortAngles([{ partnerAngleDeg: 170 }])[0]).toBeCloseTo(170)
  })

  it('wraps a partner angle on the far side of the seam without clamping it away', () => {
    // seam at 170deg; a partner at -170deg is only 20deg past the seam, not
    // on the opposite side of the circle, so it must resolve near -170/190,
    // not get clamped back down near the seam.
    const [angle] = resolveNodePortAngles([{ partnerAngleDeg: -170 }], 170)
    const normalized = ((angle % 360) + 360) % 360
    expect(normalized).toBeCloseTo(190)
  })

  it('pushes overlapping partner angles apart while preserving relative order', () => {
    const [first, second] = resolveNodePortAngles([
      { partnerAngleDeg: 10 },
      { partnerAngleDeg: 10 },
    ])

    expect(first).toBeCloseTo(10)
    expect(second).toBeGreaterThan(first)
  })

  it('never collapses many ports crowded at the same angle, and keeps them within one full turn', () => {
    const angles = resolveNodePortAngles([
      { partnerAngleDeg: 40 },
      { partnerAngleDeg: 40 },
      { partnerAngleDeg: 40 },
      { partnerAngleDeg: 40 },
      { partnerAngleDeg: 40 },
    ])

    const rounded = angles.map((a) => Math.round(a * 1000))
    expect(new Set(rounded).size).toBe(5)
    const sorted = [...angles].sort((a, b) => a - b)
    expect(sorted[sorted.length - 1] - sorted[0]).toBeLessThan(360)
  })

  it('returns an empty array for zero ports', () => {
    expect(resolveNodePortAngles([])).toEqual([])
  })
})

describe('clusterFallbackAngles', () => {
  it('returns an empty array for zero ports', () => {
    expect(clusterFallbackAngles(0, 90)).toEqual([])
  })

  it('places a single port exactly on the anchor angle', () => {
    expect(clusterFallbackAngles(1, 90)).toEqual([90])
  })

  it('spreads multiple ports symmetrically around the anchor at the given gap', () => {
    expect(clusterFallbackAngles(3, 0, 16)).toEqual([-16, 0, 16])
  })

  it('defaults to a 16 degree gap between adjacent ports', () => {
    const angles = clusterFallbackAngles(2, 0)
    expect(angles[1] - angles[0]).toBeCloseTo(16)
  })
})

describe('unconnectedPortAngles', () => {
  it('clusters inputs around the seam angle and outputs around its opposite', () => {
    const { inputAngles, outputAngles } = unconnectedPortAngles(1, 1, 40)
    expect(inputAngles).toEqual([40])
    expect(outputAngles).toEqual([220])
  })

  it('returns an empty array for a side with no unconnected ports', () => {
    const { inputAngles, outputAngles } = unconnectedPortAngles(0, 2, 0)
    expect(inputAngles).toEqual([])
    expect(outputAngles).toHaveLength(2)
  })
})

describe('labelPointFromAngleDeg', () => {
  it('sits further from the node center than the port dot at the same angle', () => {
    const dot = pointFromAngleDeg(30)
    const label = labelPointFromAngleDeg(30)
    const dotDist = Math.hypot(dot.left - 56, dot.top - 56)
    const labelDist = Math.hypot(label.left - 56, label.top - 56)
    expect(labelDist).toBeGreaterThan(dotDist)
  })

  it('defaults to a 22px outward offset along the same angle as pointFromAngleDeg', () => {
    const label = labelPointFromAngleDeg(0)
    expect(label.left).toBeCloseTo(56 + 56 + 22)
    expect(label.top).toBeCloseTo(56)
  })
})

describe('connectedHandleStyle', () => {
  it('is always invisible and non-interactive', () => {
    const style = connectedHandleStyle()
    expect(style.opacity).toBe(0)
    expect(style.pointerEvents).toBe('none')
  })
})

describe('revealableHandleStyle', () => {
  it('is visible and interactive when revealed', () => {
    const style = revealableHandleStyle('#fff', true)
    expect(style.opacity).toBe(1)
    expect(style.pointerEvents).toBe('auto')
  })

  it('is hidden and non-interactive when not revealed', () => {
    const style = revealableHandleStyle('#fff', false)
    expect(style.opacity).toBe(0)
    expect(style.pointerEvents).toBe('none')
  })
})
