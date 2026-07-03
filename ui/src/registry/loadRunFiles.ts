import { RunFileSchema, RunFileContentSchema } from '@/types'
import type { RunFile, RunFileContent } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

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