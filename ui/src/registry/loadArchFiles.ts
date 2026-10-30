import { ArchFileSchema, ArchListItemSchema, type ArchFile, type ArchListItem } from '@/types/arch'

// Defaults to same-origin ('') — goes through the Vite dev proxy (/api → :8000), so there is no CORS
// and no problem of the client pointing at itself when accessed over the LAN.
// (Same pattern as loadRunFiles.ts — follow this instead of the brief's VITE_API_URL absolute-path default.)
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function loadArchFiles(): Promise<ArchListItem[]> {
  const res = await fetch(`${API_BASE}/api/arch`)
  if (!res.ok) throw new Error(`Failed to list arch files: ${res.status}`)
  return ArchListItemSchema.array().parse(await res.json())
}

export async function loadArchFile(name: string): Promise<ArchFile> {
  const res = await fetch(`${API_BASE}/api/arch/${encodeURIComponent(name)}`)
  if (!res.ok) {
    // 400/404 response bodies are {"detail": "line 7: ..."} — the line number is part of the contract,
    // so it is carried into the Error message as-is (design requirement: expose line numbers in errors).
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Failed to load arch file: ${res.status}`)
  }
  return ArchFileSchema.parse(await res.json())
}
