import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useExecutionStore, useNodeRuntime } from '@/execution/useExecutionStore'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { useRegistry } from '@/registry/RegistryContext'
import type { ModelSlot, NodeRuntimeStatus, Port } from '@/types'
import type { RFNodeData } from '@/stores/useGraphStore'
import { RadialNodePorts } from './RadialNodePorts'

function AgentNodeImpl({ id, data, selected }: NodeProps) {
  const registry = useRegistry()
  const runtime = useNodeRuntime(id)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const manifest = registry.get((data as RFNodeData).manifestType)

  if (!manifest) {
    return (
      <div className="rounded-xl border border-[#ff8a80] bg-[#410005]/80 px-3 py-2 text-[12px] text-[#ffb4ab]">
        Unknown: {(data as RFNodeData).manifestType}
      </div>
    )
  }

  const meta = CATEGORY_META[manifest.category]
  const status = runtime?.status ?? 'idle'
  const config = (data as RFNodeData).config
  const modelSlots: ModelSlot[] = Array.isArray(config?.modelSlots)
    ? (config.modelSlots as ModelSlot[])
    : []
  // custom.node(Phase B④)는 매니페스트에 포트/라벨이 없다 — 인스턴스 config가 채운다.
  // 다른 타입은 config.inputs/outputs/label을 절대 안 채우므로 이 fallback은 무변화.
  const dynamicInputs: Port[] = (config?.inputs as Port[] | undefined) ?? manifest.inputs
  const dynamicOutputs: Port[] = (config?.outputs as Port[] | undefined) ?? manifest.outputs
  const label = (config?.label as string | undefined) ?? manifest.label
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
      aria-label={`${label} agent node`}
    >
      <RadialNodePorts nodeId={id} inputs={dynamicInputs} outputs={dynamicOutputs} color={meta.color} />
      <div className="pointer-events-none absolute inset-2 flex flex-col items-center justify-center rounded-full text-center">
        <span
          className="material-symbols-outlined rounded-full p-1.5"
          style={{ background: `${meta.color}1f`, color: meta.color, fontSize: 18 }}
          aria-hidden="true"
        >
          {meta.icon}
        </span>
        <span className="mt-1 max-w-[82px] truncate text-[10px] font-semibold text-[#dde4dd]">
          {label}
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
