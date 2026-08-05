import { findLoopCandidates, type LoopCandidate } from './loopCandidates'

type EdgeLike = {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
}

export type LoopCandidateView = LoopCandidate & {
  id: string
  label: string
  returnEdgeIds: string[]
}

export type LoopAnchor = {
  candidateId: string
  label: string
  role: 'feedbackSource' | 'reentryTarget'
}

const RETURN_HANDLES = new Set(['refine', 'retry', 'revise', 'rework', 'reject'])

/**
 * Cycle detection is a read model, not a policy. These views give each
 * deterministic candidate a compact canvas label without persisting anything
 * into Architecture.
 */
export function buildLoopCandidateViews(nodeIds: string[], edges: EdgeLike[]): LoopCandidateView[] {
  const candidates = findLoopCandidates(nodeIds, edges).loops
  const edgeById = new Map(edges.map((edge) => [edge.id, edge]))

  return [...candidates]
    .sort((a, b) => stableMembers(a).localeCompare(stableMembers(b)))
    .map((candidate, index) => {
      const feedbackEdgeIds = [...candidate.feedbackEdgeIds].sort()
      const returnEdgeIds = feedbackEdgeIds.filter((edgeId) =>
        RETURN_HANDLES.has(edgeById.get(edgeId)?.sourceHandle ?? ''),
      )
      const members = stableMembers(candidate)
      return {
        ...candidate,
        id: `loop:${candidate.tier}:${members}`,
        label: `L${index + 1}`,
        memberNodeIds: [...candidate.memberNodeIds].sort(),
        feedbackEdgeIds,
        returnEdgeIds,
      }
    })
}

/**
 * Each candidate contributes one source and one re-entry token per involved
 * node. A semantic return handle takes precedence; when no handle is known we
 * keep anchors visible but deliberately leave the real edge untouched.
 */
export function buildLoopAnchorsByNodeId(
  candidates: LoopCandidateView[],
  edges: EdgeLike[],
): Map<string, LoopAnchor[]> {
  const edgeById = new Map(edges.map((edge) => [edge.id, edge]))
  const anchorsByNodeId = new Map<string, LoopAnchor[]>()
  const seen = new Set<string>()

  for (const candidate of candidates) {
    const anchorEdgeIds = candidate.returnEdgeIds.length > 0
      ? candidate.returnEdgeIds
      : candidate.feedbackEdgeIds
    for (const edgeId of anchorEdgeIds) {
      const edge = edgeById.get(edgeId)
      if (!edge) continue
      appendAnchor(anchorsByNodeId, seen, edge.source, {
        candidateId: candidate.id,
        label: candidate.label,
        role: 'feedbackSource',
      })
      appendAnchor(anchorsByNodeId, seen, edge.target, {
        candidateId: candidate.id,
        label: candidate.label,
        role: 'reentryTarget',
      })
    }
  }

  return anchorsByNodeId
}

/** Only semantically named return edges are hidden in the candidate-only UI. */
export function candidateReturnEdgeIds(candidates: LoopCandidateView[]): Set<string> {
  return new Set(candidates.flatMap((candidate) => candidate.returnEdgeIds))
}

function stableMembers(candidate: LoopCandidate): string {
  return [...candidate.memberNodeIds].sort().join(',')
}

function appendAnchor(
  anchorsByNodeId: Map<string, LoopAnchor[]>,
  seen: Set<string>,
  nodeId: string,
  anchor: LoopAnchor,
) {
  const key = `${nodeId}:${anchor.candidateId}:${anchor.role}`
  if (seen.has(key)) return
  seen.add(key)
  anchorsByNodeId.set(nodeId, [...(anchorsByNodeId.get(nodeId) ?? []), anchor])
}
