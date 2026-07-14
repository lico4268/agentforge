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
      return { ...base, status: 'failed', lastError: event.error ?? base.lastError }

    case 'log': {
      // token_usage 이벤트(log)로 토큰·모델·재시도·fallback 관측치를 누적.
      // node_end는 tokenUsage를 싣지 않으므로 여기가 실제 수집 지점이다.
      const tu = event.tokenUsage
      if (!tu) return base
      return {
        ...base,
        totalTokens: base.totalTokens + (tu.prompt + tu.completion),
        lastModel: tu.model ?? base.lastModel,
        lastAttempt: tu.attempt ?? base.lastAttempt,
        fallbackUsed: tu.fallbackUsed ?? base.fallbackUsed,
      }
    }

    default:
      return base
  }
}
