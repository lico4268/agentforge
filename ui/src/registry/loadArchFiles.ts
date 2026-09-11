import { ArchFileSchema, ArchListItemSchema, type ArchFile, type ArchListItem } from '@/types/arch'

// 기본값은 same-origin('') — Vite dev 프록시(/api → :8000)를 타므로 CORS도,
// LAN 접속 시 클라이언트 자기 자신을 가리키는 문제도 생기지 않는다.
// (loadRunFiles.ts와 동일한 패턴 — 브리프의 VITE_API_URL 절대경로 기본값 대신 이걸 따른다.)
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function loadArchFiles(): Promise<ArchListItem[]> {
  const res = await fetch(`${API_BASE}/api/arch`)
  if (!res.ok) throw new Error(`Failed to list arch files: ${res.status}`)
  return ArchListItemSchema.array().parse(await res.json())
}

export async function loadArchFile(name: string): Promise<ArchFile> {
  const res = await fetch(`${API_BASE}/api/arch/${encodeURIComponent(name)}`)
  if (!res.ok) {
    // 400/404 응답 본문은 {"detail": "line 7: ..."} — 줄 번호가 계약의 일부이므로
    // 그대로 Error message에 실어 올린다 (설계 §요구사항: 에러에 줄 번호 노출).
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Failed to load arch file: ${res.status}`)
  }
  return ArchFileSchema.parse(await res.json())
}
