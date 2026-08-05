type EdgeLike = { id: string; source: string; target: string }

export type SelfLoopCandidate = { nodeId: string; edgeId: string }

export type LoopCandidate = {
  tier: 1 | 2 | 3
  memberNodeIds: string[]
  feedbackEdgeIds: string[]
}

/**
 * Tarjan's SCC algorithm. A component of size >= 2 means every member can
 * reach every other member — i.e. there's at least one cycle among them. A
 * size-1 component is only a real cycle if that node has a self-loop edge
 * (checked separately by the caller); otherwise it's just an acyclic node.
 */
export function findStronglyConnectedComponents(nodeIds: string[], edges: EdgeLike[]): string[][] {
  const adjacency = new Map<string, string[]>()
  for (const id of nodeIds) adjacency.set(id, [])
  for (const e of edges) {
    adjacency.get(e.source)?.push(e.target)
  }

  let indexCounter = 0
  const indices = new Map<string, number>()
  const lowlink = new Map<string, number>()
  const onStack = new Set<string>()
  const stack: string[] = []
  const components: string[][] = []

  function strongConnect(v: string) {
    indices.set(v, indexCounter)
    lowlink.set(v, indexCounter)
    indexCounter += 1
    stack.push(v)
    onStack.add(v)

    for (const w of adjacency.get(v) ?? []) {
      if (!indices.has(w)) {
        strongConnect(w)
        lowlink.set(v, Math.min(lowlink.get(v)!, lowlink.get(w)!))
      } else if (onStack.has(w)) {
        lowlink.set(v, Math.min(lowlink.get(v)!, indices.get(w)!))
      }
    }

    if (lowlink.get(v) === indices.get(v)) {
      const component: string[] = []
      let w: string
      do {
        w = stack.pop()!
        onStack.delete(w)
        component.push(w)
      } while (w !== v)
      components.push(component)
    }
  }

  for (const id of nodeIds) {
    if (!indices.has(id)) strongConnect(id)
  }

  return components
}

/**
 * Counts distinct simple cycles within `members` (an already-confirmed SCC),
 * capped at `cap` — Tier classification only needs "1 vs 2+", so search
 * stops the instant a second cycle is found instead of enumerating every
 * cycle in the component (Johnson-style: each cycle is only ever found once,
 * at the point where the search vertex is that cycle's minimum member, so no
 * rotation is double-counted; the blocking-set speedup Johnson's full
 * algorithm adds on top only matters once you need *every* cycle — the
 * capped early exit here sidesteps that need entirely).
 */
function countSimpleCyclesCapped(members: string[], adjacency: Map<string, string[]>, cap: number): number {
  const ordered = [...members].sort()
  let count = 0

  for (let i = 0; i < ordered.length && count < cap; i += 1) {
    const start = ordered[i]
    const allowed = new Set(ordered.slice(i))
    const visited = new Set<string>([start])

    const dfs = (current: string): void => {
      if (count >= cap) return
      for (const next of adjacency.get(current) ?? []) {
        if (count >= cap) return
        if (!allowed.has(next)) continue
        if (next === start) {
          count += 1
          continue
        }
        if (visited.has(next)) continue
        visited.add(next)
        dfs(next)
        visited.delete(next)
      }
    }

    dfs(start)
  }

  return count
}

/**
 * The Slice 7 read model: classifies each cyclic part of the graph into a
 * Loop Scope tier. Self-loops are reported separately (they're the "single
 * node retry" affordance, not a Loop Scope container).
 */
export function findLoopCandidates(
  nodeIds: string[],
  edges: EdgeLike[],
): { loops: LoopCandidate[]; selfLoops: SelfLoopCandidate[] } {
  const selfLoops: SelfLoopCandidate[] = edges
    .filter((e) => e.source === e.target)
    .map((e) => ({ nodeId: e.source, edgeId: e.id }))

  const nonSelfEdges = edges.filter((e) => e.source !== e.target)
  const components = findStronglyConnectedComponents(nodeIds, nonSelfEdges)

  const loops: LoopCandidate[] = []
  for (const members of components) {
    if (members.length < 2) continue

    const memberSet = new Set(members)
    const adjacency = new Map<string, string[]>()
    for (const id of members) adjacency.set(id, [])
    const feedbackEdgeIds: string[] = []
    for (const e of nonSelfEdges) {
      if (memberSet.has(e.source) && memberSet.has(e.target)) {
        adjacency.get(e.source)!.push(e.target)
        feedbackEdgeIds.push(e.id)
      }
    }

    const cycleCount = countSimpleCyclesCapped(members, adjacency, 2)
    const tier: 1 | 2 | 3 = cycleCount >= 2 ? 3 : members.length === 2 ? 1 : 2

    loops.push({ tier, memberNodeIds: members, feedbackEdgeIds })
  }

  return { loops, selfLoops }
}
