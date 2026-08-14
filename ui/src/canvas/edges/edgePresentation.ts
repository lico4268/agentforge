const CONDITIONAL_HANDLES = new Set(['accept', 'refine', 'clarify', 'approve', 'revise', 'reject'])

const LOOP_BACK_HANDLE = 'loopBack'

/**
 * True when this edge is `loop.guard`'s re-entry edge — the one structural
 * signal every compiled graph guarantees for a cycle (an ungated cycle is a
 * compile error, see docs/superpowers/specs/2026-08-07-loop-node-design.md
 * §4), so no screen-position heuristic is needed to find it.
 */
export function isLoopBackEdge(sourceHandle?: string | null): boolean {
  return sourceHandle === LOOP_BACK_HANDLE
}

export function edgePresentation(sourceHandle?: string | null) {
  const conditional = Boolean(sourceHandle && CONDITIONAL_HANDLES.has(sourceHandle))
  const color =
    sourceHandle === 'accept' || sourceHandle === 'approve'
      ? '#4edea3'
      : sourceHandle === 'clarify' || sourceHandle === 'revise'
        ? '#ffd180'
        : sourceHandle === 'reject'
          ? '#ff8a80'
          : '#6f8175'

  return { conditional, color }
}
