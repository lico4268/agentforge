import { findLoopCandidates } from './loopCandidates'

type EdgeLike = { id: string; source: string; target: string }

/**
 * Edge-level fallback metadata for overlapping cycles. Tier 3 has no safe
 * single container, so its feedback edges remain visible and carry a loop
 * badge instead.
 */
export function findTier3FeedbackEdgeIds(nodeIds: string[], edges: EdgeLike[]): Set<string> {
  const { loops } = findLoopCandidates(nodeIds, edges)
  return new Set(
    loops
      .filter((loop) => loop.tier === 3)
      .flatMap((loop) => loop.feedbackEdgeIds),
  )
}
