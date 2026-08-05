import { useState } from 'react'
import { Handle } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'
import { useUiStore } from '@/stores/useUiStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import type { RFNode, RFNodeData } from '@/stores/useGraphStore'
import type { BoundaryPort } from '@/canvas/loops/loopScopeBoundaryPorts'
import { handleStyle, pointFromAngleDeg, positionFromAngleDeg, resolveNodePortAngles } from './radialPortGeometry'

export const LOOP_SCOPE_DIAMETER = 128

/**
 * Extends `RFNodeData` (rather than replacing it) purely so the container
 * node structurally satisfies `RFNode` — React Flow's `onNodesChange` etc.
 * are typed against `RFNode` project-wide, and this is a real node in the
 * rendered array, just a synthetic one. `manifestType`/`config` are unused
 * dummies; every real field lives below.
 */
export type LoopScopeNodeData = RFNodeData & {
  loopScopeId: string
  tier: 1 | 2
  memberNodeIds: string[]
  /** Snapshot of the real member nodes — read-only, used to look up each
   * member's category color (Tier 1 glyph) and relative layout (ghost
   * preview). Never written back to the graph store. */
  memberNodes: RFNode[]
  boundaryPorts: BoundaryPort[]
}

function memberColor(node: RFNode, registry: ReturnType<typeof useRegistry>): string {
  const manifest = registry.get((node.data as RFNodeData).manifestType)
  return manifest ? CATEGORY_META[manifest.category].color : '#3c4a42'
}

function LoopScopeNodeImpl({ data, selected }: NodeProps) {
  const { loopScopeId, tier, memberNodeIds, memberNodes, boundaryPorts } = data as unknown as LoopScopeNodeData
  const registry = useRegistry()
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const toggleLoopScopeExpanded = useUiStore((s) => s.toggleLoopScopeExpanded)
  const [hovered, setHovered] = useState(false)

  const colors = memberNodes.map((n) => memberColor(n, registry))
  const angles = resolveNodePortAngles(
    boundaryPorts.map((p) => ({ partnerAngleDeg: p.angleDeg })),
    0,
  )
  const expand = () => toggleLoopScopeExpanded(loopScopeId)

  return (
    <div
      className="relative rounded-full border-2 border-dashed bg-[#161d19]/90 shadow-lg backdrop-blur-md"
      style={{ width: LOOP_SCOPE_DIAMETER, height: LOOP_SCOPE_DIAMETER, borderColor: selected ? (colors[0] ?? '#4edea3') : '#3c4a42' }}
      role="button"
      tabIndex={0}
      aria-label={`Collapsed loop scope with ${memberNodeIds.length} members — activate to expand`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
      onClick={expand}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          expand()
        }
      }}
    >
      {boundaryPorts.map((port, index) => {
        const angle = angles[index]
        return (
          <Handle
            key={port.edgeId}
            type={port.isInput ? 'target' : 'source'}
            position={positionFromAngleDeg(angle)}
            id={port.edgeId}
            isConnectable={false}
            style={{
              ...handleStyle('#4edea3', showConnectionPorts),
              ...pointFromAngleDeg(angle),
              transform: 'translate(-50%, -50%)',
            }}
            title={`${port.isInput ? 'Entry' : 'Exit'} edge — expand this scope to add or rewire connections`}
          />
        )
      })}

      {tier === 1 ? (
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute inset-[12%] rounded-full border-2" style={{ borderColor: colors[0] ?? '#3c4a42' }} />
          <div className="absolute inset-[34%] rounded-full border-2" style={{ borderColor: colors[1] ?? '#3c4a42' }} />
        </div>
      ) : (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden="true">
          <span className="material-symbols-outlined text-[26px]" style={{ color: '#86948a' }}>
            hub
          </span>
        </div>
      )}

      <div className="pointer-events-none absolute -bottom-2 left-1/2 -translate-x-1/2 rounded-full border border-[#3c4a42] bg-[#0e1511] px-2 py-0.5 text-[9px] font-semibold text-[#dde4dd]">
        {tier === 1 ? '↻' : `${memberNodeIds.length} nodes`}
      </div>

      {hovered && <GhostLoopPreview loopScopeId={loopScopeId} memberNodes={memberNodes} colors={colors} />}
    </div>
  )
}

/** Hover/focus-only preview of the real internal cycle — lets a user glimpse
 * the feedback path without fully expanding (drill-in) the container. */
function GhostLoopPreview({
  loopScopeId,
  memberNodes,
  colors,
}: {
  loopScopeId: string
  memberNodes: RFNode[]
  colors: string[]
}) {
  if (memberNodes.length < 2) return null

  const size = LOOP_SCOPE_DIAMETER
  const center = size / 2
  const radius = size * 0.26
  const angleStep = (2 * Math.PI) / memberNodes.length
  const points = memberNodes.map((_, i) => ({
    x: center + radius * Math.cos(i * angleStep - Math.PI / 2),
    y: center + radius * Math.sin(i * angleStep - Math.PI / 2),
  }))
  const markerId = `loop-ghost-arrow-${loopScopeId}`

  return (
    <svg
      className="pointer-events-none absolute inset-0"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label="Preview of the real feedback path inside this loop scope"
    >
      <defs>
        <marker id={markerId} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill="currentColor" />
        </marker>
      </defs>
      {points.map((p, i) => {
        const next = points[(i + 1) % points.length]
        const midX = (p.x + next.x) / 2
        const midY = (p.y + next.y) / 2 - 8
        const color = colors[i] ?? '#4edea3'
        return (
          <path
            key={i}
            d={`M ${p.x} ${p.y} Q ${midX} ${midY} ${next.x} ${next.y}`}
            fill="none"
            stroke={color}
            strokeWidth={1.5}
            strokeDasharray="3 2"
            style={{ color }}
            markerEnd={`url(#${markerId})`}
          />
        )
      })}
      {points.map((p, i) => (
        <circle key={`dot-${i}`} cx={p.x} cy={p.y} r={3} fill={colors[i] ?? '#4edea3'} />
      ))}
    </svg>
  )
}

export const LoopScopeNode = LoopScopeNodeImpl
