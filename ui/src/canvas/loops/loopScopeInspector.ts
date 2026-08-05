import type { NodeRuntime } from '@/types'
import type { LoopScope } from './loopScopes'

type EdgeLike = {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

export type ScopeTransitionKind = 'trigger' | 'entry' | 'exit'

export type ScopeTransition = {
  id: string
  kind: ScopeTransitionKind
  sourceId: string
  targetId: string
  port: string | null
}

export type LoopScopeRuntimeSummary = {
  status: 'idle' | 'running' | 'failed' | 'complete'
  calls: number
  durationMs: number
  tokens: number
}

export type LoopScopeInspectorModel = {
  scope: LoopScope
  collapsed: boolean
  transitions: ScopeTransition[]
  guardStatus: 'not-configured' | 'custom-policy'
  runtime: LoopScopeRuntimeSummary
}

/**
 * Read-only Inspector projection. Loop scopes are canvas-derived and must not
 * be persisted into Architecture, so their details are reconstructed from the
 * source graph each render.
 */
export function buildLoopScopeInspectorModel(
  scope: LoopScope,
  edges: EdgeLike[],
  runtimeByNodeId: Record<string, NodeRuntime>,
  collapsed: boolean,
): LoopScopeInspectorModel {
  const feedback = new Set(scope.feedbackEdgeIds)
  const entry = new Set(scope.entryEdgeIds)
  const exit = new Set(scope.exitEdgeIds)
  const transitions = edges.flatMap((edge): ScopeTransition[] => {
    const kind: ScopeTransitionKind | null = feedback.has(edge.id)
      ? 'trigger'
      : entry.has(edge.id)
        ? 'entry'
        : exit.has(edge.id)
          ? 'exit'
          : null
    return kind
      ? [{ id: edge.id, kind, sourceId: edge.source, targetId: edge.target, port: edge.sourceHandle ?? null }]
      : []
  })

  const memberRuntimes = scope.memberNodeIds
    .map((id) => runtimeByNodeId[id])
    .filter((runtime): runtime is NodeRuntime => runtime != null)
  const status = memberRuntimes.some((runtime) => runtime.status === 'failed')
    ? 'failed'
    : memberRuntimes.some((runtime) => runtime.status === 'running')
      ? 'running'
      : memberRuntimes.some((runtime) => runtime.callCount > 0)
        ? 'complete'
        : 'idle'

  return {
    scope,
    collapsed,
    transitions,
    // An exit edge describes an application-specific route, but it is not an
    // executable per-loop guard until Architecture/WS gain that contract.
    guardStatus: scope.exitEdgeIds.length > 0 ? 'custom-policy' : 'not-configured',
    runtime: {
      status,
      calls: memberRuntimes.reduce((sum, runtime) => sum + runtime.callCount, 0),
      durationMs: memberRuntimes.reduce((sum, runtime) => sum + runtime.totalDurationMs, 0),
      tokens: memberRuntimes.reduce((sum, runtime) => sum + runtime.totalTokens, 0),
    },
  }
}
