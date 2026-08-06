import { z } from 'zod'

/**
 * Graph instance contracts — the design the user draws.
 *
 * `Architecture` is the export/import unit (ui-architecture.md §4.2). Persisting
 * in this shape from day one means v0.4 architecture-sharing only needs to add
 * import/export buttons, not change the data model.
 */

export const GraphNodeSchema = z.object({
  id: z.string(),
  /** References NodeManifest.type. */
  type: z.string(),
  position: z.object({ x: z.number(), y: z.number() }),
  config: z.record(z.string(), z.unknown()).default({}),
})
export type GraphNode = z.infer<typeof GraphNodeSchema>

export const GraphEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  sourceHandle: z.string(),
  target: z.string(),
  targetHandle: z.string(),
})
export type GraphEdge = z.infer<typeof GraphEdgeSchema>

export const LoopPolicyGuardSchema = z.object({
  maxIterations: z.number().optional(),
  maxTokens: z.number().optional(),
  maxCostUsd: z.number().optional(),
  maxDurationSec: z.number().optional(),
  stuck: z
    .object({
      window: z.number(),
      threshold: z.number().optional(),
    })
    .optional(),
})
export type LoopPolicyGuard = z.infer<typeof LoopPolicyGuardSchema>

export const LOOP_POLICY_KINDS = ['evaluatorOptimizer', 'critiqueRevise', 'humanReview'] as const
export const LOOP_POLICY_EXHAUSTION_ACTIONS = ['exit', 'escalate', 'fail'] as const

/**
 * Executable loop configuration, distinct from a detected cycle (`LoopCandidate`
 * in `canvas/loops/loopAnchors.ts`). `kind` is descriptive only — the compiler
 * never branches on it. See docs/superpowers/specs/2026-08-06-loop-policy-design.md.
 */
export const LoopPolicySchema = z.object({
  id: z.string(),
  kind: z.enum(LOOP_POLICY_KINDS),
  feedbackEdgeIds: z.array(z.string()),
  memberNodeIds: z.array(z.string()),
  exitEdgeIds: z.array(z.string()),
  guard: LoopPolicyGuardSchema,
  onExhaustion: z.enum(LOOP_POLICY_EXHAUSTION_ACTIONS),
})
export type LoopPolicy = z.infer<typeof LoopPolicySchema>

export const ArchitectureSchema = z.object({
  version: z.string().default('0.1'),
  metadata: z.object({
    name: z.string(),
    description: z.string().optional(),
    createdAt: z.string(),
  }),
  nodes: z.array(GraphNodeSchema).default([]),
  edges: z.array(GraphEdgeSchema).default([]),
  loopPolicies: z.array(LoopPolicySchema).default([]),
})
export type Architecture = z.infer<typeof ArchitectureSchema>
