import { findLoopCandidates } from './loopCandidates'

type EdgeLike = { id: string; source: string; target: string }

export type LoopScope = {
  id: string
  tier: 1 | 2
  memberNodeIds: string[]
  /** Edges with both endpoints inside the scope — hidden from the canvas
   * when collapsed, since the `↻`/`N nodes` badge represents them instead. */
  feedbackEdgeIds: string[]
  /** Edges entering the scope from outside — rerouted to the container's
   * boundary when collapsed. */
  entryEdgeIds: string[]
  /** Edges leaving the scope to the outside — rerouted to the container's
   * boundary when collapsed. */
  exitEdgeIds: string[]
  /** Members that are the target of at least one internal edge — where
   * control actually re-enters the loop. Rendered as a marker when expanded. */
  reentryNodeIds: string[]
}

/**
 * Projects Slice 7's cycle read model into the Tier 1/2 `LoopScope`s the
 * canvas can collapse into a single container. Tier 3 (overlapping cycles)
 * has no single container to collapse into, so it's excluded here — it stays
 * a set of edge-level badges instead (see LOOP_UI_PLAN.md).
 */
export function buildLoopScopes(nodeIds: string[], edges: EdgeLike[]): LoopScope[] {
  const { loops } = findLoopCandidates(nodeIds, edges)

  return loops
    .filter((loop): loop is typeof loop & { tier: 1 | 2 } => loop.tier !== 3)
    .map((loop) => {
      const memberNodeIds = [...loop.memberNodeIds].sort()
      const memberSet = new Set(memberNodeIds)
      const feedbackEdgeIds = [...loop.feedbackEdgeIds].sort()
      const feedbackEdgeSet = new Set(feedbackEdgeIds)

      const entryEdgeIds: string[] = []
      const exitEdgeIds: string[] = []
      for (const e of edges) {
        if (feedbackEdgeSet.has(e.id)) continue
        const sourceInside = memberSet.has(e.source)
        const targetInside = memberSet.has(e.target)
        if (!sourceInside && targetInside) entryEdgeIds.push(e.id)
        else if (sourceInside && !targetInside) exitEdgeIds.push(e.id)
      }

      const reentryTargets = new Set(
        edges.filter((e) => feedbackEdgeSet.has(e.id)).map((e) => e.target),
      )
      const reentryNodeIds = memberNodeIds.filter((id) => reentryTargets.has(id))

      return {
        id: `loop:${loop.tier}:${memberNodeIds.join(',')}`,
        tier: loop.tier as 1 | 2,
        memberNodeIds,
        feedbackEdgeIds,
        entryEdgeIds,
        exitEdgeIds,
        reentryNodeIds,
      }
    })
}
