import type { Edge } from '@xyflow/react'
import type { LoopCandidateView } from '@/canvas/loops/loopAnchors'
import { useRegistry } from '@/registry/RegistryContext'
import type { RFNode } from '@/stores/useGraphStore'

type Props = {
  candidate: LoopCandidateView
  nodes: RFNode[]
  edges: Edge[]
}

export function LoopCandidateInspector({ candidate, nodes, edges }: Props) {
  const registry = useRegistry()
  const labelByNodeId = new Map(nodes.map((node) => [
    node.id,
    registry.get(node.data.manifestType)?.label ?? node.id,
  ]))
  const feedbackEdges = candidate.feedbackEdgeIds
    .map((edgeId) => edges.find((edge) => edge.id === edgeId))
    .filter((edge): edge is Edge => edge != null)

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#161d19]/80 backdrop-blur-xl">
      <div className="shrink-0 border-b border-[#4c3a75]/60 px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#a78bfa]" style={{ fontSize: 18 }}>sync</span>
          <h2 className="text-[15px] font-semibold tracking-wide text-[#ede9fe]">Loop {candidate.label}</h2>
          <span className="rounded border border-[#a78bfa]/40 bg-[#7c3aed]/10 px-1.5 py-0.5 font-mono text-[9px] text-[#c4b5fd]">Candidate</span>
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[#a99fbc]">
          Detected from graph structure. A LoopPolicy has not been configured yet.
        </p>
      </div>

      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-5">
        <section className="flex flex-col gap-3">
          <SectionTitle>Loop Lens</SectionTitle>
          <div className="rounded-lg border border-[#4c3a75]/70 bg-[#120f1c] p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              {candidate.memberNodeIds.map((nodeId, index) => (
                <div key={nodeId} className="flex items-center gap-1.5">
                  {index > 0 && <span className="material-symbols-outlined text-[13px] text-[#a78bfa]" aria-hidden="true">arrow_forward</span>}
                  <span className="rounded border border-[#4c3a75] bg-[#1e1930] px-2 py-1 text-[10px] text-[#ede9fe]">
                    {labelByNodeId.get(nodeId) ?? nodeId}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[10px] text-[#c4b5fd]">
              <span className="material-symbols-outlined text-[14px]" aria-hidden="true">subdirectory_arrow_left</span>
              Return paths are listed below; the main canvas keeps its forward flow uncluttered.
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <SectionTitle>Detected transitions</SectionTitle>
          {feedbackEdges.map((edge) => (
            <div key={edge.id} className="rounded border border-[#3c4a42] bg-[#242c27] px-3 py-2 text-[11px] text-[#dde4dd]">
              {labelByNodeId.get(edge.source) ?? edge.source}
              <span className="mx-1 text-[#a78bfa]">→</span>
              {labelByNodeId.get(edge.target) ?? edge.target}
              {edge.sourceHandle && <span className="ml-2 font-mono text-[9px] text-[#a99fbc]">{edge.sourceHandle}</span>}
            </div>
          ))}
        </section>

        <section className="flex flex-col gap-3">
          <SectionTitle>Policy status</SectionTitle>
          <div className="rounded-lg border border-dashed border-[#a78bfa]/40 bg-[#7c3aed]/5 p-3 text-[11px] leading-relaxed text-[#c4b5fd]">
            Set max iterations, token/cost/time budgets, exits, and exhaustion handling when the LoopPolicy runtime contract is available. Runtime values are intentionally unavailable until then.
          </div>
        </section>
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: string }) {
  return <h3 className="border-b border-[#4c3a75]/50 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#a78bfa]">{children}</h3>
}
