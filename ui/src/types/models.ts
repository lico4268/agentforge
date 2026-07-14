import { z } from 'zod'

export const ModelConfigSchema = z.object({
  id: z.string(),
  provider: z.enum(['anthropic', 'openai', 'google', 'local']),
  label: z.string(),
  description: z.string().default(''),
  /** 해당 provider의 API 키가 백엔드에 설정되어 있는지 여부 */
  available: z.boolean(),
  /** config.yaml 모델 기본값 — 노드가 override하지 않으면 상속됨 (상속 표시용) */
  temperature: z.number().optional(),
  maxTokens: z.number().optional(),
})
export type ModelConfig = z.infer<typeof ModelConfigSchema>

export const ModelConfigListSchema = z.array(ModelConfigSchema)
