import { Position } from '@xyflow/react'

const NODE_DIAMETER = 112
const NODE_RADIUS = NODE_DIAMETER / 2
const FULL_CIRCLE = 360

export type NodePortInput = {
  /** Degrees. Real direction from this node toward the port's connected
   * partner. When omitted, the port falls back to even spacing around the
   * full circle. */
  partnerAngleDeg?: number
}

/** Converts an angle (`angleDegBetween`'s convention) to a point on the node's border. */
export function pointFromAngleDeg(angleDeg: number) {
  const radians = (angleDeg * Math.PI) / 180
  return {
    left: NODE_RADIUS + NODE_RADIUS * Math.cos(radians),
    top: NODE_RADIUS - NODE_RADIUS * Math.sin(radians),
  }
}

/**
 * Real screen-space direction from `from` to `to`, expressed in the same
 * angle convention `pointFromAngleDeg` uses (0=right, 90=up on screen, since
 * screen y grows downward but this convention treats increasing angle as
 * counterclockwise). Feed the result straight into `seamAngleDeg`/
 * `partnerAngleDeg` — no further conversion needed.
 */
export function angleDegBetween(from: { x: number; y: number }, to: { x: number; y: number }): number {
  const dx = to.x - from.x
  const dy = to.y - from.y
  // `-dy || 0` avoids IEEE-754 negative zero flipping atan2 to the -180 branch
  // when `to` and `from` share the same y (e.g. a point directly to the left).
  return (Math.atan2(-dy || 0, dx) * 180) / Math.PI
}

function normalizeAngleDeg(angleDeg: number): number {
  const wrapped = angleDeg % 360
  if (wrapped > 180) return wrapped - 360
  if (wrapped <= -180) return wrapped + 360
  return wrapped
}

/**
 * Quantizes a continuous angle (`angleDegBetween`'s convention) to the
 * nearest React Flow `Position`. A port's `<Handle position=...>` must track
 * its real direction — otherwise `getBezierPath` keeps drawing the curve's
 * tangent toward a stale side even though the dot itself moved.
 */
export function positionFromAngleDeg(angleDeg: number): Position {
  const angle = normalizeAngleDeg(angleDeg)
  if (angle > -45 && angle <= 45) return Position.Right
  if (angle > 45 && angle <= 135) return Position.Top
  if (angle > 135 || angle <= -135) return Position.Left
  return Position.Bottom
}

/** Shared handle style for every port dot (real nodes and collapsed loop
 * scope containers alike) — hidden by default, revealed only in connection
 * edit mode (`useUiStore.showConnectionPorts`). */
export function handleStyle(color: string, visible: boolean) {
  return {
    width: 10,
    height: 10,
    background: '#0e1511',
    border: `2px solid ${color}`,
    borderRadius: '50%',
    opacity: visible ? 1 : 0,
    pointerEvents: visible ? 'auto' : 'none',
  } as const
}

/** Wraps `angle` into `[seam, seam + 360)`. */
function wrapIntoTurnFrom(angle: number, seam: number): number {
  return seam + (((angle - seam) % FULL_CIRCLE) + FULL_CIRCLE) % FULL_CIRCLE
}

/**
 * Resolves each port's angle around the node's FULL circle — there is no
 * input/output hemisphere split. Direction is conveyed by the edge's
 * arrowhead now, not by which side of the node a port sits on, so every port
 * (input or output) shares the same 360-degree pool and is biased toward its
 * real partner angle. Overlapping ideal angles are pushed apart while
 * preserving their relative order, wrapping around the circle instead of
 * clamping to a boundary. Falls back to even spacing when no partner angle
 * is known. Returned in the same order as `ports`.
 *
 * `seamAngleDeg` is only where the circle is conceptually "cut" for sorting —
 * it doesn't forbid placement there. The hub-facing direction (opposite the
 * rim) is a natural, low-traffic choice: partners rarely sit back toward the
 * graph's own center.
 */
export function resolveNodePortAngles(ports: NodePortInput[], seamAngleDeg = 0): number[] {
  const total = ports.length
  if (total === 0) return []

  const start = seamAngleDeg
  const end = start + FULL_CIRCLE
  const minGap = FULL_CIRCLE / total

  const idealAngles = ports.map((port, index) => {
    const fallback = start + ((index + 0.5) / total) * FULL_CIRCLE
    const ideal = port.partnerAngleDeg ?? fallback
    return wrapIntoTurnFrom(ideal, start)
  })

  const order = idealAngles.map((_, index) => index).sort((a, b) => idealAngles[a] - idealAngles[b])
  const sorted = order.map((index) => idealAngles[index])

  for (let i = 1; i < total; i += 1) {
    if (sorted[i] < sorted[i - 1] + minGap) sorted[i] = sorted[i - 1] + minGap
  }
  if (sorted[total - 1] > end) {
    sorted[total - 1] = end
    for (let i = total - 2; i >= 0; i -= 1) {
      if (sorted[i] > sorted[i + 1] - minGap) sorted[i] = sorted[i + 1] - minGap
    }
  }

  const anglesByOriginalIndex = new Array<number>(total)
  order.forEach((originalIndex, sortedIndex) => {
    anglesByOriginalIndex[originalIndex] = sorted[sortedIndex]
  })

  return anglesByOriginalIndex
}
