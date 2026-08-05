import { useStoreWithEqualityFn } from 'zustand/traditional'
import { useGraphStore } from '@/stores/useGraphStore'
import { angleDegBetween } from './radialPortGeometry'

const DEFAULT_NODE_DIAMETER = 112

type XY = { x: number; y: number }
type PortLike = { id: string }
type NodeLike = { id: string; position: XY }
type EdgeLike = {
  source: string
  sourceHandle?: string | null
  target: string
  targetHandle?: string | null
}

export type HubRimAngles = {
  /** Degrees, in `angleDegBetween`'s convention. Direction from the radial
   * center toward this node — feed straight into `resolveNodePortAngles`'s
   * `seamAngleDeg` (the hub-facing direction, opposite this, is a natural,
   * low-traffic place to "cut" the circle for sorting). 0 when there is no
   * radial center or this node is it. */
  rimAngleDeg: number
  /** Degrees, keyed by port id. Only present for ports with a connected
   * edge; absent ports fall back to even spacing around the full circle. */
  partnerAngleDegByPortId: Record<string, number>
}

const FALLBACK: HubRimAngles = { rimAngleDeg: 0, partnerAngleDegByPortId: {} }

function centerPointOf(node: NodeLike, diameter: number): XY {
  return { x: node.position.x + diameter / 2, y: node.position.y + diameter / 2 }
}

/**
 * Pure bridge from graph topology (node positions + edges) to the angles
 * `radialPortGeometry` needs. Kept free of React/store dependencies so the
 * angle logic is testable with plain data — `useHubRimAngles` below is the
 * thin, non-tested wiring on top.
 */
export function computeHubRimAngles(params: {
  nodeId: string
  ports: PortLike[]
  side: 'input' | 'output'
  radialCenterId: string | null
  nodes: NodeLike[]
  edges: EdgeLike[]
  nodeDiameter?: number
}): HubRimAngles {
  const { nodeId, ports, side, radialCenterId, nodes, edges, nodeDiameter = DEFAULT_NODE_DIAMETER } = params

  if (!radialCenterId || radialCenterId === nodeId) return FALLBACK

  const self = nodes.find((n) => n.id === nodeId)
  const center = nodes.find((n) => n.id === radialCenterId)
  if (!self || !center) return FALLBACK

  const selfPoint = centerPointOf(self, nodeDiameter)
  const rimAngleDeg = angleDegBetween(centerPointOf(center, nodeDiameter), selfPoint)

  const partnerAngleDegByPortId: Record<string, number> = {}
  for (const port of ports) {
    const edge =
      side === 'input'
        ? edges.find((e) => e.target === nodeId && e.targetHandle === port.id)
        : edges.find((e) => e.source === nodeId && e.sourceHandle === port.id)
    if (!edge) continue

    const partnerId = side === 'input' ? edge.source : edge.target
    const partner = nodes.find((n) => n.id === partnerId)
    if (!partner) continue

    partnerAngleDegByPortId[port.id] = angleDegBetween(selfPoint, centerPointOf(partner, nodeDiameter))
  }

  return { rimAngleDeg, partnerAngleDegByPortId }
}

function hubRimAnglesEqual(a: HubRimAngles, b: HubRimAngles): boolean {
  if (a.rimAngleDeg !== b.rimAngleDeg) return false
  const aKeys = Object.keys(a.partnerAngleDegByPortId)
  const bKeys = Object.keys(b.partnerAngleDegByPortId)
  if (aKeys.length !== bKeys.length) return false
  return aKeys.every((key) => a.partnerAngleDegByPortId[key] === b.partnerAngleDegByPortId[key])
}

/**
 * Reads the current radial center, this node, and its connected partners from
 * the graph store. Uses a tailored equality check (not `useShallow`, which
 * can't see into the nested per-port record) so this node only re-renders
 * when its own rim/partner angles actually change — not on every unrelated
 * node's drag frame, since `applyNodeChanges` preserves object identity for
 * nodes it doesn't touch.
 */
export function useHubRimAngles(nodeId: string, ports: PortLike[], side: 'input' | 'output'): HubRimAngles {
  return useStoreWithEqualityFn(
    useGraphStore,
    (s) =>
      computeHubRimAngles({
        nodeId,
        ports,
        side,
        radialCenterId: s.radialCenterId,
        nodes: s.nodes,
        edges: s.edges,
      }),
    hubRimAnglesEqual,
  )
}
