import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useExecutionStore, useNodeRuntime } from '@/execution/useExecutionStore'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { useRegistry } from '@/registry/RegistryContext'
import { useUiStore } from '@/stores/useUiStore'
import type { ModelSlot, NodeRuntimeStatus } from '@/types'
import type { RFNodeData } from '@/stores/useGraphStore'
import { RadialNodePorts } from './RadialNodePorts'

/** Loop-scope annotations `Canvas.tsx` stamps onto a member node's `data`
 * while its scope is expanded — never persisted (`toArchitecture` reads
 * straight from the graph store, not from this projected view). */
type LoopAnnotatedData = RFNodeData & {
  loopReentry?: boolean
  loopScopeCollapseAffordance?: string
}

function AgentNodeImpl({ id, data, selected }: NodeProps) {
  const registry = useRegistry()
  const runtime = useNodeRuntime(id)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const toggleLoopScopeExpanded = useUiStore((s) => s.toggleLoopScopeExpanded)
  const manifest = registry.get((data as RFNodeData).manifestType)
  const { loopReentry, loopScopeCollapseAffordance } = data as LoopAnnotatedData

  if (!manifest) {
    return (
      <div className="rounded-xl border border-[#ff8a80] bg-[#410005]/80 px-3 py-2 text-[12px] text-[#ffb4ab]">
        Unknown: {(data as RFNodeData).manifestType}
      </div>
    )
  }

  const meta = CATEGORY_META[manifest.category]
  const status = runtime?.status ?? 'idle'
  const modelSlots: ModelSlot[] = Array.isArray((data as RFNodeData).config?.modelSlots)
    ? ((data as RFNodeData).config.modelSlots as ModelSlot[])
    : []
  const isPendingCheckpoint =
    manifest.type === 'human.checkpoint' && pendingInterrupt?.nodeId === id
  const borderColor = selected ? meta.color : statusColor(status, meta.color)

  return (
    <div
      className="relative h-[112px] w-[112px] rounded-full border bg-[#161d19]/90 shadow-lg backdrop-blur-md"
      style={{
        borderColor,
        boxShadow:
          status === 'running'
            ? `0 0 0 1px ${meta.color}88, 0 0 18px ${meta.color}44`
            : selected
              ? `0 0 0 1px ${meta.color}66`
              : undefined,
      }}
      aria-label={`${manifest.label} agent node`}
    >
      <RadialNodePorts nodeId={id} inputs={manifest.inputs} outputs={manifest.outputs} color={meta.color} />
      <div className="pointer-events-none absolute inset-2 flex flex-col items-center justify-center rounded-full text-center">
        <span
          className="material-symbols-outlined rounded-full p-1.5"
          style={{ background: `${meta.color}1f`, color: meta.color, fontSize: 18 }}
          aria-hidden="true"
        >
          {meta.icon}
        </span>
        <span className="mt-1 max-w-[82px] truncate text-[10px] font-semibold text-[#dde4dd]">
          {manifest.label}
        </span>
        <div className="mt-1 flex items-center gap-1 font-mono text-[8px] text-[#86948a]">
          <StatusLabel status={status} />
          {manifest.maxModelSlots && <span>{modelSlots.length}/{manifest.maxModelSlots}</span>}
        </div>
      </div>
      {isPendingCheckpoint && (
        <span
          className="absolute bottom-2 right-2 h-2.5 w-2.5 rounded-full border border-[#161d19] bg-[#ffd180] shadow-[0_0_8px_rgba(255,209,128,0.85)]"
          title="Review decision required in Inspector"
          aria-label="Review decision required in Inspector"
        />
      )}
      {loopReentry && (
        <span
          className="absolute bottom-2 left-2 flex h-4 w-4 items-center justify-center rounded-full border border-[#161d19] bg-[#4edea3] text-[9px] font-bold text-[#0e1511]"
          title="Re-entry point — control returns here from within the loop"
          aria-label="Loop re-entry point"
        >
          ↩
        </span>
      )}
      {loopScopeCollapseAffordance && (
        <button
          type="button"
          className="nodrag absolute -top-2 left-1/2 -translate-x-1/2 rounded-full border border-[#3c4a42] bg-[#0e1511] px-1.5 py-0.5 text-[8px] font-semibold text-[#86948a] hover:text-[#dde4dd]"
          onClick={(e) => {
            e.stopPropagation()
            toggleLoopScopeExpanded(loopScopeCollapseAffordance)
          }}
          title="Collapse this loop scope back into a single node"
        >
          collapse ↺
        </button>
      )}
    </div>
  )
}

function statusColor(status: NodeRuntimeStatus, accent: string) {
  switch (status) {
    case 'running':
      return accent
    case 'success':
      return '#4edea3'
    case 'failed':
      return '#ff8a80'
    case 'skipped':
      return '#3c4a42'
    default:
      return 'rgba(255,255,255,0.08)'
  }
}

function StatusLabel({ status }: { status: NodeRuntimeStatus }) {
  if (status === 'idle') return null

  const label = status === 'success' ? 'done' : status
  const color = statusColor(status, '#ffd180')
  return (
    <span className="flex items-center gap-0.5" aria-label={`Status: ${label}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  )
}

export const AgentNode = memo(AgentNodeImpl)
