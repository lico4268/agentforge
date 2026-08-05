import { useMemo, type ReactNode } from 'react'
import type { Edge } from '@xyflow/react'
import { buildLoopScopeInspectorModel, type ScopeTransition } from '@/canvas/loops/loopScopeInspector'
import type { LoopScope } from '@/canvas/loops/loopScopes'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { useRegistry } from '@/registry/RegistryContext'
import type { RFNode } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'

type Props = {
  scope: LoopScope
  nodes: RFNode[]
  edges: Edge[]
}

export function LoopScopeInspector({ scope, nodes, edges }: Props) {
  const registry = useRegistry()
  const runtimeByNodeId = useExecutionStore((s) => s.runtimeByNodeId)
  const expandedLoopScopeIds = useUiStore((s) => s.expandedLoopScopeIds)
  const collapsed = !expandedLoopScopeIds.has(scope.id)
  const model = useMemo(
    () => buildLoopScopeInspectorModel(scope, edges, runtimeByNodeId, collapsed),
    [collapsed, edges, runtimeByNodeId, scope],
  )
  const labelByNodeId = useMemo(
    () => new Map(nodes.map((node) => [
      node.id,
      registry.get(node.data.manifestType)?.label ?? node.id,
    ])),
    [nodes, registry],
  )
  const scopeLabel = `Loop scope · ${scope.memberNodeIds.length} nodes`

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#161d19]/80 backdrop-blur-xl">
      <div className="relative shrink-0 overflow-hidden border-b border-[#3c4a42]/50 px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#4edea3]" style={{ fontSize: 18 }}>cycle</span>
          <h2 className="text-[15px] font-semibold tracking-wide text-[#dde4dd]">{scopeLabel}</h2>
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[#86948a]">
          Derived canvas view. It does not change the execution graph.
        </p>
      </div>

      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-5">
        <Section title="Scope">
          <Detail label="Tier" value={`Tier ${scope.tier}`} />
          <Detail label="Display" value={model.collapsed ? 'Collapsed' : 'Expanded'} />
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] text-[#86948a]">Members</span>
            <div className="flex flex-wrap gap-1.5">
              {scope.memberNodeIds.map((id) => (
                <span key={id} className="rounded border border-[#3c4a42] bg-[#242c27] px-2 py-0.5 font-mono text-[10px] text-[#bbcabf]">
                  {labelByNodeId.get(id) ?? id}
                </span>
              ))}
            </div>
          </div>
        </Section>

        <Section title="Transitions">
          <TransitionList
            label="Trigger"
            transitions={model.transitions.filter((transition) => transition.kind === 'trigger')}
            labelByNodeId={labelByNodeId}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] text-[#86948a]">Re-entry</span>
            <span className="text-[11px] text-[#dde4dd]">
              {scope.reentryNodeIds.map((id) => labelByNodeId.get(id) ?? id).join(', ') || 'Not detected'}
            </span>
          </div>
          <TransitionList
            label="Entry"
            transitions={model.transitions.filter((transition) => transition.kind === 'entry')}
            labelByNodeId={labelByNodeId}
          />
          <TransitionList
            label="Exit"
            transitions={model.transitions.filter((transition) => transition.kind === 'exit')}
            labelByNodeId={labelByNodeId}
          />
        </Section>

        <Section title="Guard">
          <div className="rounded border border-[#ffd180]/30 bg-[#ffd180]/5 px-3 py-2 text-[11px] text-[#ffd180]">
            {model.guardStatus === 'custom-policy'
              ? 'Custom policy — exit transitions exist, but no executable per-loop guard is configured.'
              : 'Not configured — this scope has no declared exit condition or per-loop guard.'}
          </div>
          <p className="text-[10px] leading-relaxed text-[#86948a]">
            Max iterations, budget, and fallback are not configured. LangGraph recursion limits are graph-wide safety limits; they are not a loop guard.
          </p>
        </Section>

        <Section title="Runtime">
          <div className="grid grid-cols-2 gap-2">
            <Metric label="Status" value={model.runtime.status} />
            <Metric label="Member calls" value={String(model.runtime.calls)} />
            <Metric label="Duration" value={`${model.runtime.durationMs} ms`} />
            <Metric label="Tokens" value={String(model.runtime.tokens)} />
          </div>
          <div className="rounded border border-[#3c4a42] bg-[#242c27] px-3 py-2 text-[11px] text-[#86948a]">
            Iteration and last feedback are not available: execution events do not yet report loop counters or edge traversal.
          </div>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">{title}</h3>
      {children}
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="text-[#86948a]">{label}</span>
      <span className="font-mono text-[#dde4dd]">{value}</span>
    </div>
  )
}

function TransitionList({
  label,
  transitions,
  labelByNodeId,
}: {
  label: string
  transitions: ScopeTransition[]
  labelByNodeId: Map<string, string>
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] text-[#86948a]">{label}</span>
      {transitions.length === 0 ? (
        <span className="text-[11px] text-[#dde4dd]">None</span>
      ) : (
        transitions.map((transition) => (
          <span key={transition.id} className="font-mono text-[10px] text-[#dde4dd]">
            {labelByNodeId.get(transition.sourceId) ?? transition.sourceId}
            {transition.port ? ` (${transition.port})` : ''} → {labelByNodeId.get(transition.targetId) ?? transition.targetId}
          </span>
        ))
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded border border-[#3c4a42]/60 bg-[#242c27] p-2">
      <span className="font-mono text-[10px] uppercase tracking-wider text-[#86948a]">{label}</span>
      <span className="font-mono text-[12px] text-[#dde4dd]">{value}</span>
    </div>
  )
}
