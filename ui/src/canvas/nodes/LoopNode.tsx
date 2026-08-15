import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useUiStore } from '@/stores/useUiStore'
import { useGraphStore } from '@/stores/useGraphStore'
import { useExecutionStore, useNodeRuntime } from '@/execution/useExecutionStore'
import { LOOP_ACCENT_COLOR } from '@/lib/categoryStyle'
import type { NodeRuntimeStatus } from '@/types'
import type { LoopCollapsedNodeData } from '@/canvas/loop/loopProjection'
import { RadialNodePorts } from './RadialNodePorts'

/**
 * Canvas representation of a collapsed loop: a ripple halo (two fading
 * loop-purple rings) marks it as "this is a container" regardless of
 * execution status; the inner circle's border follows the same
 * running/success/failed/skipped language every other node uses, just with
 * loop-purple as its accent instead of a category color. Double-click drills
 * into the loop's real internals (Canvas.tsx's projectDrilledInView).
 */
function LoopNodeImpl({ id, data, selected }: NodeProps) {
  const runtime = useNodeRuntime(id)
  const enterLoop = useUiStore((s) => s.enterLoop)
  const radialCenterId = useGraphStore((s) => s.radialCenterId)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const { memberCount, memberIds, loopInputs, loopOutputs, portView } = data as LoopCollapsedNodeData

  const status = runtime?.status ?? 'idle'
  const borderColor = selected ? LOOP_ACCENT_COLOR : statusColor(status, LOOP_ACCENT_COLOR)
  const hasPendingCheckpointInside =
    pendingInterrupt !== null && memberIds.includes(pendingInterrupt.nodeId)

  return (
    <div
      className="relative h-[112px] w-[112px]"
      onDoubleClick={() => enterLoop(id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') enterLoop(id)
      }}
      aria-label={`Loop, ${memberCount} node${memberCount === 1 ? '' : 's'} inside — activate to open`}
    >
      {/* Ripple halo — fixed loop-purple identity rings, independent of status */}
      <div
        className="pointer-events-none absolute rounded-full"
        style={{ inset: -20, border: `1px solid ${LOOP_ACCENT_COLOR}`, opacity: 0.12 }}
      />
      <div
        className="pointer-events-none absolute rounded-full"
        style={{ inset: -8, border: `1.2px solid ${LOOP_ACCENT_COLOR}`, opacity: 0.22 }}
      />

      <div
        className="relative h-[112px] w-[112px] rounded-full border bg-[#161d19]/90 shadow-lg backdrop-blur-md"
        style={{ borderColor, borderWidth: 2.5 }}
      >
        <RadialNodePorts
          nodeId={id}
          inputs={loopInputs}
          outputs={loopOutputs}
          color={LOOP_ACCENT_COLOR}
          viewOverride={{ nodes: portView.nodes, edges: portView.edges, radialCenterId }}
        />
        <div className="pointer-events-none absolute inset-2 flex flex-col items-center justify-center rounded-full text-center">
          <span className="text-[10px] font-semibold text-[#dde4dd]">Loop</span>
          <span className="mt-1 font-mono text-[8px] text-[#86948a]">
            {memberCount} node{memberCount === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {hasPendingCheckpointInside && (
        <span
          className="absolute bottom-2 right-2 h-2.5 w-2.5 rounded-full border border-[#161d19] bg-[#ffd180] shadow-[0_0_8px_rgba(255,209,128,0.85)]"
          title="A checkpoint inside this loop needs a decision — open it to review"
          aria-label="A checkpoint inside this loop needs a decision"
        />
      )}

      <span
        className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border bg-[#0e1511] opacity-55 transition-opacity hover:opacity-100"
        style={{ borderColor: LOOP_ACCENT_COLOR, color: LOOP_ACCENT_COLOR }}
        title="Double-click to open this loop"
      >
        <span className="material-symbols-outlined" style={{ fontSize: 12 }}>open_in_full</span>
      </span>
    </div>
  )
}

function statusColor(status: NodeRuntimeStatus, accent: string) {
  switch (status) {
    case 'running': return accent
    case 'success': return '#4edea3'
    case 'failed':  return '#ff8a80'
    case 'skipped': return '#3c4a42'
    default:        return 'rgba(255,255,255,0.08)'
  }
}

export const LoopNode = memo(LoopNodeImpl)
