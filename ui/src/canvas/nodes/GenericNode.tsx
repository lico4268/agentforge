import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useRegistry } from '@/registry/RegistryContext'
import { useNodeRuntime } from '@/execution/useExecutionStore'
import { CATEGORY_META } from '@/lib/categoryStyle'
import type { NodeRuntimeStatus } from '@/types'
import type { RFNodeData } from '@/stores/useGraphStore'
import { NodeInputs, NodeOutputs } from './NodePorts'

function GenericNodeImpl({ id, data, selected }: NodeProps) {
  const registry = useRegistry()
  const runtime  = useNodeRuntime(id)
  const manifest = registry.get((data as RFNodeData).manifestType)

  if (!manifest) {
    return (
      <div className="rounded-lg border border-[#ff8a80] bg-[#410005]/80 px-3 py-2 text-[12px] text-[#ffb4ab]">
        Unknown: {(data as RFNodeData).manifestType}
      </div>
    )
  }

  const meta   = CATEGORY_META[manifest.category]
  const status = runtime?.status ?? 'idle'
  const isRunning = status === 'running'

  const borderColor = selected
    ? meta.color
    : statusBorderColor(status, meta.color)

  const glowStyle = isRunning
    ? { boxShadow: `0 0 0 1px ${meta.color}88, 0 0 20px ${meta.color}44` }
    : selected
    ? { boxShadow: `0 0 0 1px ${meta.color}66` }
    : {}

  return (
    <div
      className="min-w-[200px] overflow-hidden rounded-lg border backdrop-blur-md"
      style={{
        background: 'rgba(22, 29, 25, 0.85)',
        borderColor,
        ...glowStyle,
        transition: 'border-color 0.2s ease, box-shadow 0.25s ease',
      }}
    >
      {/* 2px top accent bar */}
      <div style={{ height: 2, background: meta.color, opacity: 0.9 }} />

      {/* Input handles */}
      <NodeInputs inputs={manifest.inputs} color={meta.color} />

      {/* Header */}
      <div
        className="flex items-center justify-between gap-2 px-3 py-2"
        style={{ background: `${meta.color}18` }}
      >
        <div className="flex items-center gap-2">
          <span
            className="material-symbols-outlined shrink-0"
            style={{ fontSize: 14, color: meta.color }}
          >
            {meta.icon}
          </span>
          <span className="text-[12px] font-semibold text-[#dde4dd]">{manifest.label}</span>
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Stats footer */}
      {runtime && runtime.callCount > 0 && (
        <div className="flex items-center justify-between border-t border-[#3c4a42]/40 px-3 py-1 font-mono text-[10px] text-[#86948a]">
          <span>{runtime.totalDurationMs} ms</span>
          <span>{runtime.totalTokens} tok</span>
        </div>
      )}

      {/* Output handles */}
      <NodeOutputs outputs={manifest.outputs} color={meta.color} />
    </div>
  )
}

function statusBorderColor(status: NodeRuntimeStatus, accent: string) {
  switch (status) {
    case 'running': return accent
    case 'success': return '#4edea3'
    case 'failed':  return '#ff8a80'
    case 'skipped': return '#3c4a42'
    default:        return 'rgba(255,255,255,0.08)'
  }
}

function StatusBadge({ status }: { status: NodeRuntimeStatus }) {
  if (status === 'idle') return null
  const map: Record<NodeRuntimeStatus, { text: string; color: string; icon: string }> = {
    idle:    { text: '',          color: '',        icon: ''              },
    running: { text: 'running',   color: '#ffd180', icon: 'hourglass_top' },
    success: { text: 'done',      color: '#4edea3', icon: 'check_circle'  },
    failed:  { text: 'failed',    color: '#ff8a80', icon: 'error'         },
    skipped: { text: 'skipped',   color: '#86948a', icon: 'block'         },
  }
  const s = map[status]
  return (
    <span
      className={`flex items-center gap-0.5 font-mono text-[9px] font-medium${status === 'running' ? ' node-running' : ''}`}
      style={{ color: s.color }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 10, fontVariationSettings: "'FILL' 1" }}>
        {s.icon}
      </span>
      {s.text}
    </span>
  )
}

export const GenericNode = memo(GenericNodeImpl)
