import { OpenRouterCatalogSchema, type OpenRouterCatalogEntry } from '@/types'

const CATALOG_URL = '/api/openrouter/catalog'
const FAVORITES_URL = '/api/openrouter/favorites'

/** 즐겨찾기 선택 화면용 — OpenRouter 전체 라이브 카탈로그. */
export async function loadOpenRouterCatalog(): Promise<OpenRouterCatalogEntry[]> {
  const res = await fetch(CATALOG_URL)
  if (!res.ok) throw new Error(`${CATALOG_URL} ${res.status}`)
  return OpenRouterCatalogSchema.parse(await res.json())
}

export async function loadOpenRouterFavorites(): Promise<string[]> {
  const res = await fetch(FAVORITES_URL)
  if (!res.ok) throw new Error(`${FAVORITES_URL} ${res.status}`)
  return res.json()
}

/** 노드 UI/Inspector 모델 슬롯에 노출할 OpenRouter 모델 id 목록을 갱신. */
export async function saveOpenRouterFavorites(ids: string[]): Promise<string[]> {
  const res = await fetch(FAVORITES_URL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  })
  if (!res.ok) throw new Error(`${FAVORITES_URL} ${res.status}`)
  return res.json()
}
