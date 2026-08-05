import type { LoopScope } from './loopScopes'

type XY = { x: number; y: number }
type NodeLike = { id: string; position: XY }
type EdgeLike = {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

export type LoopScopeProjectionResult<N, C, E> = {
  nodes: (N | C)[]
  edges: E[]
  /** Real member node ids to render a re-entry marker on — only populated for
   * scopes currently expanded (a collapsed scope shows its own badge instead). */
  reentryNodeIds: Set<string>
  /** For each expanded scope, the one designated member node that should carry
   * the "collapse back" affordance (avoids stamping every member with a
   * duplicate control). */
  collapseAffordanceNodeIdByScopeId: Record<string, string>
}

function centroid(positions: XY[]): XY {
  const sum = positions.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 })
  return { x: sum.x / positions.length, y: sum.y / positions.length }
}

/**
 * Projects the real graph into what the canvas actually renders: Tier 1/2
 * `LoopScope`s not in `expandedScopeIds` collapse their members into a single
 * container node (built by the caller-supplied `createContainerNode`, so this
 * module never needs to know the app's node `data` shape). Internal feedback
 * edges are dropped (the container's badge represents them); entry/exit edges
 * reroute to the container, keyed by the edge's own id so multiple boundary
 * edges never collide on a single handle id.
 *
 * Expanded scopes pass their members and edges through untouched, and instead
 * report which members should carry a re-entry marker / collapse affordance —
 * left for the caller to merge into its own node `data`, for the same reason.
 */
export function projectLoopScopes<N extends NodeLike, C extends NodeLike, E extends EdgeLike>(
  nodes: N[],
  edges: E[],
  loopScopes: LoopScope[],
  expandedScopeIds: ReadonlySet<string>,
  createContainerNode: (scope: LoopScope, position: XY, memberNodes: N[]) => C,
): LoopScopeProjectionResult<N, C, E> {
  const collapsedScopes = loopScopes.filter((s) => !expandedScopeIds.has(s.id))
  const expandedScopes = loopScopes.filter((s) => expandedScopeIds.has(s.id))

  const containerIdByMemberId = new Map<string, string>()
  for (const scope of collapsedScopes) {
    for (const memberId of scope.memberNodeIds) containerIdByMemberId.set(memberId, scope.id)
  }

  const nodesById = new Map(nodes.map((n) => [n.id, n]))
  const containerNodes = collapsedScopes.map((scope) => {
    const memberNodes = scope.memberNodeIds.map((id) => nodesById.get(id)).filter((n): n is N => n != null)
    return createContainerNode(scope, centroid(memberNodes.map((n) => n.position)), memberNodes)
  })

  const hiddenMemberIds = new Set(containerIdByMemberId.keys())
  const projectedNodes: (N | C)[] = [...nodes.filter((n) => !hiddenMemberIds.has(n.id)), ...containerNodes]

  const projectedEdges: E[] = []
  for (const e of edges) {
    const sourceContainerId = containerIdByMemberId.get(e.source)
    const targetContainerId = containerIdByMemberId.get(e.target)
    // Both endpoints collapsed into the *same* container: a purely internal
    // feedback edge, represented by the container's badge instead.
    if (sourceContainerId && sourceContainerId === targetContainerId) continue

    if (!sourceContainerId && !targetContainerId) {
      projectedEdges.push(e)
      continue
    }
    projectedEdges.push({
      ...e,
      source: sourceContainerId ?? e.source,
      sourceHandle: sourceContainerId ? e.id : e.sourceHandle,
      target: targetContainerId ?? e.target,
      targetHandle: targetContainerId ? e.id : e.targetHandle,
    })
  }

  const reentryNodeIds = new Set<string>()
  const collapseAffordanceNodeIdByScopeId: Record<string, string> = {}
  for (const scope of expandedScopes) {
    for (const id of scope.reentryNodeIds) reentryNodeIds.add(id)
    collapseAffordanceNodeIdByScopeId[scope.id] = [...scope.memberNodeIds].sort()[0]
  }

  return { nodes: projectedNodes, edges: projectedEdges, reentryNodeIds, collapseAffordanceNodeIdByScopeId }
}
