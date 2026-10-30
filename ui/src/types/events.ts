import { z } from 'zod'

/**
 * Execution event contracts — what the backend streams over WebSocket.
 *
 * Mirrors agentforge.md's core event structure. `runId`, `callIndex`,
 * `parentAgent`, and `policyDecision` are present from the start so that
 * v0.3 (local re-run, agent→agent flow) and v0.5 (branching) layer on without
 * changing the model. See ui-architecture.md §4.3.
 */

export const EXECUTION_EVENT_TYPES = [
  'node_start',
  'node_end',
  'tool_call',
  'agent_action',
  'log',
  'error',
  // backend-emitted
  'policy_decision',
  'token_usage',
  'decision_record',
  'interrupt',
] as const

export const TokenUsageSchema = z.object({
  prompt: z.number(),
  completion: z.number(),
  /** Model name actually used (for observability) */
  model: z.string().optional(),
  /** Index of the successful attempt (0 = first attempt) — shows retry count */
  attempt: z.number().optional(),
  /** Whether the call was handled by the fallback model */
  fallbackUsed: z.boolean().optional(),
})
export type TokenUsage = z.infer<typeof TokenUsageSchema>

/** Why a review/policy node activated or skipped — v0.1's key portfolio signal. */
export const PolicyDecisionSchema = z.object({
  activated: z.boolean(),
  reason: z.string(),
  /** review node verdict: accept / refine / clarify */
  branch: z.string().optional(),
  /** Whether clarify was demoted to accept in batch_mode */
  demoted: z.boolean().optional(),
})
export type PolicyDecision = z.infer<typeof PolicyDecisionSchema>

/** Structured failure detail — backend make_error_event() {type, detail}. */
export const ExecutionErrorSchema = z.object({
  type: z.string(),
  detail: z.string(),
})
export type ExecutionError = z.infer<typeof ExecutionErrorSchema>

// Only 'maxIterations' | 'budget' | 'stuck' are reachable on the wire today —
// server/nodes/loop_guard.py's evaluate_loop_guard never emits 'success' (it
// omits exitReason entirely when should_continue is true) or 'escalated', and
// the 'fail' onExhaustion path raises before any event can carry 'failed'.
// Keeping the unreachable values in the enum is a deliberate reserved-for-later
// choice, not an oversight — see server/graphs/compile.py's loop.guard branch.
export const LOOP_RUNTIME_EXIT_REASONS = [
  'success',
  'maxIterations',
  'budget',
  'stuck',
  'escalated',
  'failed',
] as const

/** Per-pass snapshot emitted by a `loop.guard` canvas node — see
 * docs/superpowers/specs/2026-08-07-loop-node-design.md §8. `loopNodeId` is the
 * real canvas node id, identical to the event's own `nodeId`, so consumers can
 * treat guard events exactly like any other node's events. */
export const LoopRuntimeSchema = z.object({
  loopNodeId: z.string(),
  iteration: z.number(),
  maxIterations: z.number().optional(),
  tokens: z.number().optional(),
  costUsd: z.number().optional(),
  durationMs: z.number().optional(),
  lastFeedback: z.string().optional(),
  exitReason: z.enum(LOOP_RUNTIME_EXIT_REASONS).optional(),
})
export type LoopRuntime = z.infer<typeof LoopRuntimeSchema>

export const ExecutionEventSchema = z.object({
  eventType: z.enum(EXECUTION_EVENT_TYPES),
  runId: z.string(),
  nodeId: z.string(),
  agentId: z.string().optional(),
  /** Who triggered this node — drives agent→agent flow view (v0.3). */
  parentAgent: z.string().optional(),
  /** Nth invocation of this node within the run — edge thickness (v0.3). */
  callIndex: z.number().optional(),
  durationMs: z.number().optional(),
  input: z.unknown().optional(),
  output: z.unknown().optional(),
  tokenUsage: TokenUsageSchema.optional(),
  policyDecision: PolicyDecisionSchema.optional(),
  loopRuntime: LoopRuntimeSchema.optional(),
  message: z.string().optional(),
  error: ExecutionErrorSchema.optional(),
  timestamp: z.string(),
})
export type ExecutionEvent = z.infer<typeof ExecutionEventSchema>

/** Runtime status derived from events by the eventReducer (not sent raw). */
export type NodeRuntimeStatus =
  | 'idle'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped'

export type NodeRuntime = {
  status: NodeRuntimeStatus
  callCount: number
  totalDurationMs: number
  totalTokens: number
  lastInput?: unknown
  lastOutput?: unknown
  policyDecision?: PolicyDecision
  lastError?: ExecutionError
  /** Model name of the last successful call (for observability) */
  lastModel?: string
  /** Attempt index of the last successful call (0 = first attempt) — shows retries */
  lastAttempt?: number
  /** Whether the last call was handled by the fallback model */
  fallbackUsed?: boolean
}

export const EMPTY_RUNTIME: NodeRuntime = {
  status: 'idle',
  callCount: 0,
  totalDurationMs: 0,
  totalTokens: 0,
}
