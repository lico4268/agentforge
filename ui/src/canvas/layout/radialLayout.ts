import type { Edge } from '@xyflow/react'

type Position = { x: number; y: number }

type LayoutNode = {
  id: string
  position: Position
}

export type RadialLayoutOptions = {
  centerId: string
  nodeDiameter?: number
  ringGap?: number
  /** Returns the actual render diameter for a node (e.g. a collapsed Loop
   * Scope unit is larger than a plain node). Falls back to `nodeDiameter`
   * for any id it doesn't recognize. */
  getNodeDiameter?: (id: string) => number
}

const PORT_GAP = 28

/**
 * Places graph neighbors in rings around one center node. Edges are treated as
 * undirected for spatial proximity; their persisted direction remains unchanged.
 */
export function radialLayout(
  nodes: LayoutNode[],
  edges: Edge[],
  { centerId, nodeDiameter = 112, ringGap = 88, getNodeDiameter }: RadialLayoutOptions,
): Record<string, Position> {
  const diameterOf = (id: string) => getNodeDiameter?.(id) ?? nodeDiameter
  const centerNode = nodes.find((node) => node.id === centerId)
  if (!centerNode) return {}

  const adjacency = new Map(nodes.map((node) => [node.id, new Set<string>()]))
  for (const edge of edges) {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  }

  const depthById = new Map<string, number>([[centerId, 0]])
  const queue = [centerId]
  for (let index = 0; index < queue.length; index += 1) {
    const id = queue[index]
    const depth = depthById.get(id)!
    for (const neighbor of adjacency.get(id) ?? []) {
      if (!depthById.has(neighbor)) {
        depthById.set(neighbor, depth + 1)
        queue.push(neighbor)
      }
    }
  }

  const maxDepth = Math.max(...depthById.values())
  for (const node of nodes) {
    if (!depthById.has(node.id)) depthById.set(node.id, maxDepth + 1)
  }

  const centerDiameter = diameterOf(centerId)
  const center = {
    x: centerNode.position.x + centerDiameter / 2,
    y: centerNode.position.y + centerDiameter / 2,
  }
  const rings = new Map<number, LayoutNode[]>()
  for (const node of nodes) {
    const depth = depthById.get(node.id)!
    if (depth === 0) continue
    const ring = rings.get(depth) ?? []
    ring.push(node)
    rings.set(depth, ring)
  }

  const positions: Record<string, Position> = { [centerId]: centerNode.position }
  let previousRingOuterRadius = centerDiameter / 2
  for (const depth of [...rings.keys()].sort((a, b) => a - b)) {
    const ring = rings.get(depth)!
    ring.sort((a, b) => {
      const angleA = Math.atan2(a.position.y - center.y, a.position.x - center.x)
      const angleB = Math.atan2(b.position.y - center.y, b.position.x - center.x)
      return angleA - angleB || a.id.localeCompare(b.id)
    })

    const ringMaxDiameter = Math.max(...ring.map((node) => diameterOf(node.id)))
    const circumferenceRadius =
      ring.reduce((sum, node) => sum + diameterOf(node.id) + PORT_GAP, 0) / (2 * Math.PI)
    const radius = Math.max(
      previousRingOuterRadius + ringGap + ringMaxDiameter / 2,
      circumferenceRadius,
    )

    let cumulative = 0
    const totalArc = ring.reduce((sum, node) => sum + diameterOf(node.id) + PORT_GAP, 0)
    for (const node of ring) {
      const diameter = diameterOf(node.id)
      const nodeArc = diameter + PORT_GAP
      const midpointFraction = (cumulative + nodeArc / 2) / totalArc
      const angle = -Math.PI / 2 + midpointFraction * Math.PI * 2
      cumulative += nodeArc
      positions[node.id] = {
        x: center.x + Math.cos(angle) * radius - diameter / 2,
        y: center.y + Math.sin(angle) * radius - diameter / 2,
      }
    }

    previousRingOuterRadius = radius + ringMaxDiameter / 2
  }

  return positions
}
