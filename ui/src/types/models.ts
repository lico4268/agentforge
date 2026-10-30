import { z } from 'zod'

export const ModelConfigSchema = z.object({
  id: z.string(),
  provider: z.enum(['anthropic', 'openai', 'google', 'local', 'openrouter']),
  label: z.string(),
  description: z.string().default(''),
  /** Whether the backend has an API key configured for this provider */
  available: z.boolean(),
  /** config.yaml model default — inherited unless a node overrides it (for display of inheritance) */
  temperature: z.number().optional(),
  maxTokens: z.number().optional(),
})
export type ModelConfig = z.infer<typeof ModelConfigSchema>

export const ModelConfigListSchema = z.array(ModelConfigSchema)

/** Live catalog entry for the OpenRouter favorites picker. Maps to server/openrouter_catalog.py. */
export const OpenRouterCatalogEntrySchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().default(''),
  contextLength: z.number().nullable().optional(),
})
export type OpenRouterCatalogEntry = z.infer<typeof OpenRouterCatalogEntrySchema>
export const OpenRouterCatalogSchema = z.array(OpenRouterCatalogEntrySchema)
