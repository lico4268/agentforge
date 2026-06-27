import { z } from 'zod'

/**
 * Node type contracts — shared with the backend.
 *
 * A `NodeManifest` describes a *node type* (not an instance). The backend owns
 * these (one manifest per plugin node); the frontend renders nodes generically
 * from them. See ui-architecture.md §4.1 / §5.
 */

export const NODE_CATEGORIES = [
  'cognitive',
  'memory',
  'model',
  'tool',
  'policy',
  'io',
] as const

export const NodeCategorySchema = z.enum(NODE_CATEGORIES)
export type NodeCategory = z.infer<typeof NodeCategorySchema>

/** A typed connection point on a node. */
export const PortSchema = z.object({
  id: z.string(),
  label: z.string(),
  /** Data type carried by this port: "text" | "messages" | "plan" | "any" ... */
  dataType: z.string(),
  required: z.boolean().optional().default(false),
})
export type Port = z.infer<typeof PortSchema>

/**
 * A single configuration field for a node. This is a deliberately small subset
 * of JSON Schema — enough to render a form, not a full validator. The backend
 * remains the source of truth for validation.
 */
export const ConfigFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum(['string', 'text', 'number', 'boolean', 'select']),
  default: z.unknown().optional(),
  options: z.array(z.object({ label: z.string(), value: z.string() })).optional(),
  placeholder: z.string().optional(),
  description: z.string().optional(),
})
export type ConfigField = z.infer<typeof ConfigFieldSchema>

export const NodeManifestSchema = z.object({
  /** Unique type id, e.g. "planning.task_decomposition". */
  type: z.string(),
  category: NodeCategorySchema,
  label: z.string(),
  description: z.string().default(''),
  inputs: z.array(PortSchema).default([]),
  outputs: z.array(PortSchema).default([]),
  config: z.array(ConfigFieldSchema).default([]),
  /** Optional custom renderer key; falls back to GenericNode when absent. */
  ui: z.object({ component: z.string().optional() }).optional(),
})
export type NodeManifest = z.infer<typeof NodeManifestSchema>

export const NodeManifestListSchema = z.array(NodeManifestSchema)
