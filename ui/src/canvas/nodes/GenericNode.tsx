import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useRegistry } from '@/registry/RegistryContext'
import { useNodeRuntime } from '@/execution/useExecutionStore'
import { CATEGORY_META } from '@/lib/categoryStyle'
import type { NodeRuntimeStatus } from '@/types'
import type { RFNodeData } from '@/stores/useGraphStore'
import { NodeInputs, NodeOutputs } from './NodePorts'

/**
 * Manifest-driven node for top-to-bottom flow.
 * Layout: [input handles TOP] → [header] → [stats] → [output handles BOTTOM]
 * Subscribes to its own runtime via selector — only this node re-renders on events.
 */
function GenericNodeImpl({ id, data, selected }: NodeProps) {
  const registry = useRegistry()
  const runtime = useNodeRuntime(id)
  const manifest = registry.get((data as RFNodeData).manifestType)

  if (!manifest) {
    return (
      <div className="rounded-md border border-red-500 bg-red-950 px-3 py-2 text-xs text-red-200">
        Unknown node: {(data as RFNodeData).manifestType}
      </div>
    )
  }

  const meta = CATEGORY_META[manifest.category]
  const status = runtime?.status ?? 'idle'

  return (
    <div
      className="min-w-[200px] rounded-lg border bg-[#11151f] shadow-lg transition-shadow"
      style={{
        borderColor: selected ? meta.color : statusBorder(status, meta.color),
        boxShadow:
          status === 'running'
            ? `0 0 0 2px ${meta.color}, 0 0 18px ${meta.color}66`
            : undefined,
      }}
    >
      {/* Input handles — top edge */}
      <NodeInputs inputs={manifest.inputs} />

      {/* Header */}
      <div
        className="flex items-center justify-between gap-2 px-3 py-1.5"
        style={{ background: `${meta.color}22` }}
      >
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: meta.color }}
          />
          <span className="text-xs font-semibold text-slate-100">
            {manifest.label}
          </span>
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Footer stats */}
      {runtime && runtime.callCount > 0 && (
        <div className="flex items-center justify-between border-t border-white/5 px-3 py-1 text-[10px] text-slate-500">
          <span>{runtime.totalDurationMs} ms</span>
          <span>{runtime.totalTokens} tok</span>
        </div>
      )}

      {/* Output handles — bottom edge */}
      <NodeOutputs outputs={manifest.outputs} />
    </div>
  )
}

function statusBorder(status: NodeRuntimeStatus, accent: string) {
  switch (status) {
    case 'running': return accent
    case 'success': return '#10b981'
    case 'failed':  return '#ef4444'
    case 'skipped': return '#475569'
    default:        return '#222a38'
  }
}

function StatusBadge({ status }: { status: NodeRuntimeStatus }) {
  if (status === 'idle') return null
  const map: Record<NodeRuntimeStatus, { text: string; color: string }> = {
    idle:    { text: '',           color: ''        },
    running: { text: '● running',  color: '#fbbf24' },
    success: { text: '✓ done',     color: '#10b981' },
    failed:  { text: '✕ failed',   color: '#ef4444' },
    skipped: { text: '⊘ skipped',  color: '#64748b' },
  }
  const s = map[status]
  return (
    <span className="text-[9px] font-medium" style={{ color: s.color }}>
      {s.text}
    </span>
  )
}

export const GenericNode = memo(GenericNodeImpl)
