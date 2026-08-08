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

/**
 * Loop 노드(`loop.guard`) manifest의 `kind` / `onExhaustion` select 옵션 소스.
 * guard 모양과는 무관한 순수 문자열 목록이다 — 노드 config 자체는 다른 노드 타입과
 * 마찬가지로 `GraphNodeSchema.config`(타입 검증 없는 record)에 담긴다.
 * See docs/superpowers/specs/2026-08-07-loop-node-design.md §2.
 */
export const LOOP_POLICY_KINDS = ['evaluatorOptimizer', 'critiqueRevise', 'humanReview'] as const
export const LOOP_POLICY_EXHAUSTION_ACTIONS = ['exit', 'escalate', 'fail'] as const

export const ArchitectureSchema = z.object({
  version: z.string().default('0.1'),
  metadata: z.object({
    name: z.string(),
    description: z.string().optional(),
    createdAt: z.string(),
  }),
  nodes: z.array(GraphNodeSchema).default([]),
  edges: z.array(GraphEdgeSchema).default([]),
})
export type Architecture = z.infer<typeof ArchitectureSchema>
