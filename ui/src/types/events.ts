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
})
export type TokenUsage = z.infer<typeof TokenUsageSchema>

/** Why a Policy node activated or skipped — v0.1's key portfolio signal. */
export const PolicyDecisionSchema = z.object({
  activated: z.boolean(),
  reason: z.string(),
})
export type PolicyDecision = z.infer<typeof PolicyDecisionSchema>

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
  message: z.string().optional(),
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
}

export const EMPTY_RUNTIME: NodeRuntime = {
  status: 'idle',
  callCount: 0,
  totalDurationMs: 0,
  totalTokens: 0,
}
