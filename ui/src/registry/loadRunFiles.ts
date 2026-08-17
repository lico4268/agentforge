import { RunFileSchema, RunFileContentSchema } from '@/types'
import type { RunFile, RunFileContent } from '@/types'

// 기본값은 same-origin('') — Vite dev 프록시(/api → :8000)를 타므로 CORS도,
// LAN 접속 시 클라이언트 자기 자신을 가리키는 문제도 생기지 않는다.
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function loadRunFiles(runId: string): Promise<RunFile[]> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/files`)
  if (!res.ok) throw new Error(`Failed to load run files: ${res.status}`)
  const data = await res.json()
  return RunFileSchema.array().parse(data)
}

export async function loadRunFileContent(
  runId: string,
  name: string,
): Promise<RunFileContent> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/files/${name}`)
  if (!res.ok) throw new Error(`Failed to load file: ${res.status}`)
  const data = await res.json()
  return RunFileContentSchema.parse(data)
}