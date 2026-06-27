import { ModelConfigListSchema, type ModelConfig } from '@/types'

const MODELS_URL = '/api/models'

/** 백엔드 모델 목록을 fetch. 실패 시 빈 배열 반환 (Toolbar가 fallback 처리). */
export async function loadModels(): Promise<ModelConfig[]> {
  const res = await fetch(MODELS_URL)
  if (!res.ok) throw new Error(`/api/models ${res.status}`)
  return ModelConfigListSchema.parse(await res.json())
}
