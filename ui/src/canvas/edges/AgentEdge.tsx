import { useState } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  useInternalNode,
  type EdgeProps,
  type InternalNode,
} from '@xyflow/react'
import { edgePresentation } from './edgePresentation'

/** Center of a node's bounding box, in the same flow-space coordinates as
 * `sourceX`/`targetX`. Falls back to the handle-based point (still correct,
 * just boundary-anchored) for the one render frame before the node is
 * measured. */
function nodeCenter(node: InternalNode | undefined, fallbackX: number, fallbackY: number) {
  if (!node) return { x: fallbackX, y: fallbackY }
  const { x, y } = node.internals.positionAbsolute
  const width = node.measured?.width ?? 0
  const height = node.measured?.height ?? 0
  return { x: x + width / 2, y: y + height / 2 }
}

export function AgentEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourceHandleId,
  markerEnd,
  selected,
  data,
}: EdgeProps) {
  const [isHovered, setIsHovered] = useState(false)
  // Collapsing a loop reroutes an outgoing edge's sourceHandle onto a
  // synthetic port id (edge.id) so RadialNodePorts can find it — but that
  // means it no longer names the real branch (accept/clarify/…). loopProjection
  // stashes the original handle in data.branchHandle for exactly this: display
  // purposes prefer it over the rerouted sourceHandleId.
  const labelHandle = typeof data?.branchHandle === 'string' ? data.branchHandle : sourceHandleId
  const { conditional, color } = edgePresentation(labelHandle)

  // Straight center-to-center. Crowded nodes push a port's angle away from
  // its partner's true direction (resolveNodePortAngles's minGap spacing),
  // so anchoring the line at the port dot itself made it cross the node
  // boundary off-angle — visibly "leaking" out of the rim instead of
  // pointing straight at the target. The node's own opaque circle covers
  // the inner half of a center-to-center line, so it still reads as
  // emerging from the boundary, just always at the correct angle.
  const sourceNode = useInternalNode(source)
  const targetNode = useInternalNode(target)
  const sourceCenter = nodeCenter(sourceNode, sourceX, sourceY)
  const targetCenter = nodeCenter(targetNode, targetX, targetY)
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX: sourceCenter.x,
    sourceY: sourceCenter.y,
    targetX: targetCenter.x,
    targetY: targetCenter.y,
  })

  const showLabel = conditional || selected || isHovered
  const stroke = selected ? '#dde4dd' : color
  const arrowMarkerId = `agent-arrow-${id}`

  return (
    <>
      <defs>
        <marker
          id={arrowMarkerId}
          markerWidth="10"
          markerHeight="10"
          refX="8"
          refY="5"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={stroke} />
        </marker>
      </defs>
      <g onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
        <BaseEdge
          id={id}
          path={edgePath}
          markerEnd={markerEnd ?? `url(#${arrowMarkerId})`}
          interactionWidth={24}
          style={{
            stroke,
            strokeWidth: selected ? 2.5 : conditional ? 2 : 1.5,
          }}
        />
      </g>
      {showLabel && sourceHandleId && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold shadow-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              color: stroke,
            }}
          >
            {labelHandle}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
