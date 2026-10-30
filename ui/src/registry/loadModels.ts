import { ModelConfigListSchema, type ModelConfig } from '@/types'

const MODELS_URL = '/api/models'

/** Fetch the backend model list. Returns an empty array on failure (Toolbar handles the fallback). */
export async function loadModels(): Promise<ModelConfig[]> {
  const res = await fetch(MODELS_URL)
  if (!res.ok) throw new Error(`/api/models ${res.status}`)
  return ModelConfigListSchema.parse(await res.json())
}
