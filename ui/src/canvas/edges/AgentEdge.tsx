import { useState } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react'
import { edgePresentation } from './edgePresentation'
import { tier3LoopLaneRoute, type Tier3LoopLane } from '@/canvas/loops/tier3LoopLane'

export function AgentEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  sourceHandleId,
  markerEnd,
  selected,
  data,
}: EdgeProps) {
  const [isHovered, setIsHovered] = useState(false)
  const { conditional, color } = edgePresentation(sourceHandleId)
  const isFeedbackLoop = sourceY > targetY
  const loopFeedback = isLoopFeedbackData(data)
  const loopLane = loopLaneFromData(data)
  const fallbackPath = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: isFeedbackLoop ? 0.42 : 0.24,
  })
  const laneRoute = loopLane
    ? tier3LoopLaneRoute(
        { x: sourceX, y: sourceY },
        { x: targetX, y: targetY },
        loopLane,
        loopLane.offset,
      )
    : null
  const edgePath = laneRoute?.path ?? fallbackPath[0]
  const labelX = laneRoute?.labelX ?? fallbackPath[1]
  const labelY = laneRoute?.labelY ?? fallbackPath[2]
  const showLabel = conditional || loopFeedback || selected || isHovered
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
            strokeDasharray: loopLane ? '7 4' : undefined,
          }}
        />
      </g>
      {showLabel && (sourceHandleId || loopFeedback) && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold shadow-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              color: stroke,
            }}
          >
            {sourceHandleId ?? 'feedback'}{loopFeedback ? ' ↻' : ''}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

function isLoopFeedbackData(data: unknown): boolean {
  return typeof data === 'object' && data !== null && (data as { loopFeedback?: unknown }).loopFeedback === true
}

type LoopLaneData = Tier3LoopLane & { offset: number }

function loopLaneFromData(data: unknown): LoopLaneData | null {
  if (typeof data !== 'object' || data === null) return null
  const lane = (data as { loopLane?: unknown }).loopLane
  if (typeof lane !== 'object' || lane === null) return null
  const candidate = lane as Partial<LoopLaneData>
  if (
    typeof candidate.outerRadius !== 'number'
    || typeof candidate.offset !== 'number'
    || typeof candidate.center?.x !== 'number'
    || typeof candidate.center.y !== 'number'
  ) return null
  return candidate as LoopLaneData
}
