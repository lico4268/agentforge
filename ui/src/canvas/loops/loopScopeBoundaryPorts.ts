import { angleDegBetween } from '../nodes/radialPortGeometry'
import type { LoopScope } from './loopScopes'

type XY = { x: number; y: number }
type EdgeLike = { id: string; source: string; target: string }

export type BoundaryPort = { edgeId: string; isInput: boolean; angleDeg: number }

/**
 * Real screen-direction angle from the container's center toward each
 * boundary edge's external partner — feeds straight into
 * `resolveNodePortAngles`, the same as a real node's ports, so a collapsed
 * container points its boundary ports toward their actual partners instead of
 * needing a separate geometry model.
 */
export function computeBoundaryPortAngles(
  containerCenter: XY,
  scope: Pick<LoopScope, 'entryEdgeIds' | 'exitEdgeIds'>,
  edges: EdgeLike[],
  centerPointById: Map<string, XY>,
): BoundaryPort[] {
  const edgesById = new Map(edges.map((e) => [e.id, e]))
  const ports: BoundaryPort[] = []

  for (const edgeId of scope.entryEdgeIds) {
    const edge = edgesById.get(edgeId)
    const partnerCenter = edge && centerPointById.get(edge.source)
    if (!edge || !partnerCenter) continue
    ports.push({ edgeId, isInput: true, angleDeg: angleDegBetween(containerCenter, partnerCenter) })
  }
  for (const edgeId of scope.exitEdgeIds) {
    const edge = edgesById.get(edgeId)
    const partnerCenter = edge && centerPointById.get(edge.target)
    if (!edge || !partnerCenter) continue
    ports.push({ edgeId, isInput: false, angleDeg: angleDegBetween(containerCenter, partnerCenter) })
  }

  return ports
}
