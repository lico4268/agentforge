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
