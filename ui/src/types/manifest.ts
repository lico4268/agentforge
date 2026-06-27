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
  'human',
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
  required: z.boolean().optional(),
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
  // 'model-id': provider 필드 값에 따라 /api/models 기반 동적 드롭다운
  type: z.enum(['string', 'text', 'number', 'boolean', 'select', 'string[]', 'model-id'] as const),
  default: z.unknown().optional(),
  // 백엔드가 문자열 배열로 보낼 수도 있으므로 두 형태를 모두 허용하고 객체 배열로 정규화
  options: z
    .array(z.union([z.object({ label: z.string(), value: z.string() }), z.string()]))
    .transform((opts) => opts.map((o) => (typeof o === 'string' ? { label: o, value: o } : o)))
    .optional(),
  placeholder: z.string().optional(),
  description: z.string().optional(),
})
export type ConfigField = z.infer<typeof ConfigFieldSchema>

const RUNTIMES = ['llm_step', 'policy', 'checkpoint', 'model', 'io'] as const

export const NodeManifestSchema = z.object({
  /** Unique type id, e.g. "planning.decompose". */
  type: z.string(),
  /** LangGraph 매핑 결정자 — category는 팔레트 표시용. */
  runtime: z.enum(RUNTIMES).optional(),
  category: NodeCategorySchema,
  label: z.string(),
  description: z.string().default(''),
  inputs: z.array(PortSchema).default([]),
  outputs: z.array(PortSchema).default([]),
  config: z.array(ConfigFieldSchema).default([]),
  /** llm_step 프리셋 기본값 (systemPrompt / outputSchema / inline model). */
  defaults: z
    .object({
      systemPrompt: z.string().optional(),
      outputSchema: z.record(z.string(), z.string()).optional(),
      model: z
        .object({ provider: z.string(), model: z.string(), temperature: z.number() })
        .optional(),
    })
    .optional(),
  /** Optional custom renderer key; falls back to GenericNode when absent. */
  ui: z.object({ component: z.string().optional() }).optional(),
})
export type NodeManifest = z.infer<typeof NodeManifestSchema>

export const NodeManifestListSchema = z.array(NodeManifestSchema)
