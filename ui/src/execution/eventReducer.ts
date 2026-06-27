import {
  EMPTY_RUNTIME,
  type ExecutionEvent,
  type NodeRuntime,
} from '@/types'

/**
 * Folds a single execution event into a node's runtime state — the frontend
 * counterpart to agentforge.md's "Canvas renderer: events → node state".
 * Pure: same store calls it for live events and for replay. See §8.
 */
export function reduceEvent(
  prev: NodeRuntime | undefined,
  event: ExecutionEvent,
): NodeRuntime {
  const base = prev ?? EMPTY_RUNTIME

  switch (event.eventType) {
    case 'node_start':
      return { ...base, status: 'running' }

    case 'node_end': {
      const skipped = event.policyDecision?.activated === false
      return {
        ...base,
        status: skipped ? 'skipped' : 'success',
        callCount: base.callCount + 1,
        totalDurationMs: base.totalDurationMs + (event.durationMs ?? 0),
        totalTokens:
          base.totalTokens +
          (event.tokenUsage
            ? event.tokenUsage.prompt + event.tokenUsage.completion
            : 0),
        lastInput: event.input ?? base.lastInput,
        lastOutput: event.output ?? base.lastOutput,
        policyDecision: event.policyDecision ?? base.policyDecision,
      }
    }

    case 'error':
      return { ...base, status: 'failed' }

    default:
      return base
  }
}
