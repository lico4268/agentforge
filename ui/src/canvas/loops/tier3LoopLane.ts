type Point = { x: number; y: number }

type PositionedNode = {
  id: string
  position: Point
}

export type Tier3LoopLane = {
  center: Point
  outerRadius: number
}

export type Tier3LoopRoute = {
  path: string
  labelX: number
  labelY: number
}

const DEFAULT_NODE_DIAMETER = 112
const DEFAULT_RING_GAP = 88

/**
 * The outer annulus is derived from the data-space radial layout, never from
 * viewport coordinates. When Arrange radially changes the center or rings,
 * this value changes with it on the next render.
 */
export function computeTier3LoopLane(
  nodes: PositionedNode[],
  radialCenterId: string | null,
  nodeDiameter = DEFAULT_NODE_DIAMETER,
  ringGap = DEFAULT_RING_GAP,
): Tier3LoopLane | null {
  if (nodes.length === 0) return null

  const centerNode = radialCenterId ? nodes.find((node) => node.id === radialCenterId) : undefined
  const center = centerNode
    ? nodeCenter(centerNode, nodeDiameter)
    : nodes.reduce(
        (sum, node) => {
          const point = nodeCenter(node, nodeDiameter)
          return { x: sum.x + point.x / nodes.length, y: sum.y + point.y / nodes.length }
        },
        { x: 0, y: 0 },
      )
  const outermostNodeCenterDistance = Math.max(
    ...nodes.map((node) => distance(center, nodeCenter(node, nodeDiameter))),
  )

  return {
    center,
    outerRadius: outermostNodeCenterDistance + nodeDiameter / 2 + ringGap,
  }
}

/** Draws source → annulus → target, with the label anchored on the arc. */
export function tier3LoopLaneRoute(
  source: Point,
  target: Point,
  lane: Tier3LoopLane,
  laneOffset = 0,
): Tier3LoopRoute {
  const radius = lane.outerRadius + laneOffset
  const sourceAngle = Math.atan2(source.y - lane.center.y, source.x - lane.center.x)
  const targetAngle = Math.atan2(target.y - lane.center.y, target.x - lane.center.x)
  const laneSource = pointOnCircle(lane.center, radius, sourceAngle)
  const laneTarget = pointOnCircle(lane.center, radius, targetAngle)
  const clockwiseDelta = normalizeAngle(targetAngle - sourceAngle)
  const clockwise = clockwiseDelta <= Math.PI
  const arcAngle = clockwise ? clockwiseDelta : Math.PI * 2 - clockwiseDelta
  const midpointAngle = sourceAngle + (clockwise ? 1 : -1) * arcAngle / 2
  const label = pointOnCircle(lane.center, radius, midpointAngle)

  // An arc command with identical endpoints has no defined direction. A short
  // radial lane is still clearer than falling back to a crossing Bezier path.
  const arc = Math.abs(sourceAngle - targetAngle) < 0.0001
    ? `L ${laneTarget.x} ${laneTarget.y}`
    : `A ${radius} ${radius} 0 0 ${clockwise ? 1 : 0} ${laneTarget.x} ${laneTarget.y}`

  return {
    path: `M ${source.x} ${source.y} L ${laneSource.x} ${laneSource.y} ${arc} L ${target.x} ${target.y}`,
    labelX: label.x,
    labelY: label.y,
  }
}

function nodeCenter(node: PositionedNode, diameter: number): Point {
  return { x: node.position.x + diameter / 2, y: node.position.y + diameter / 2 }
}

function pointOnCircle(center: Point, radius: number, angle: number): Point {
  return {
    x: center.x + Math.cos(angle) * radius,
    y: center.y + Math.sin(angle) * radius,
  }
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function normalizeAngle(angle: number): number {
  const fullTurn = Math.PI * 2
  return ((angle % fullTurn) + fullTurn) % fullTurn
}
