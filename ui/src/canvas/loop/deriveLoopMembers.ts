export type LoopGraphEdge = {
  source: string
  sourceHandle?: string | null
  target: string
}

/** The node a `loop.guard`'s `loopBack` output re-enters the loop body at —
 * the loop's "start" for boundary-marker purposes. `null` if the guard's
 * loopBack port isn't wired to anything. */
export function findLoopBackTarget(edges: LoopGraphEdge[], loopNodeId: string): string | null {
  return edges.find((e) => e.source === loopNodeId && e.sourceHandle === 'loopBack')?.target ?? null
}

/**
 * The set of nodes that make up one loop's body: everything reachable
 * forward from the guard's `loopBack` target that can also reach back to the
 * guard. Mirrors `_derive_loop_members` in `server/graphs/compile.py`
 * (forward ∩ backward from the guard) so the canvas and the compiler agree
 * on what "inside the loop" means. The guard node itself is never included —
 * it's the loop's controller, not a hidden member.
 */
export function deriveLoopMembers(
  nodeIds: string[],
  edges: LoopGraphEdge[],
  loopNodeId: string,
): string[] {
  const loopBackTarget = findLoopBackTarget(edges, loopNodeId)
  if (loopBackTarget === null) return []

  const outgoing = new Map<string, string[]>()
  const incoming = new Map<string, string[]>()
  for (const edge of edges) {
    ;(outgoing.get(edge.source) ?? outgoing.set(edge.source, []).get(edge.source)!).push(edge.target)
    ;(incoming.get(edge.target) ?? incoming.set(edge.target, []).get(edge.target)!).push(edge.source)
  }

  // Forward: reachable from the loopBack target, without crossing back
  // through the guard (the guard is the loop's boundary, not a member).
  const forward = new Set<string>()
  const forwardStack = [loopBackTarget]
  while (forwardStack.length > 0) {
    const current = forwardStack.pop()!
    if (current === loopNodeId || forward.has(current)) continue
    forward.add(current)
    for (const next of outgoing.get(current) ?? []) forwardStack.push(next)
  }

  // Backward: nodes that can reach the guard at all (walking edges in reverse).
  const backward = new Set<string>()
  const backwardStack = [loopNodeId]
  while (backwardStack.length > 0) {
    const current = backwardStack.pop()!
    if (backward.has(current)) continue
    backward.add(current)
    for (const prev of incoming.get(current) ?? []) backwardStack.push(prev)
  }

  // Filtering nodeIds (rather than iterating the sets) keeps the result in a
  // stable, caller-predictable order for tests and for badge/label rendering.
  return nodeIds.filter((id) => forward.has(id) && backward.has(id))
}
