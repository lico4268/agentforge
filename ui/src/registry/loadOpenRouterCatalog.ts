import { OpenRouterCatalogSchema, type OpenRouterCatalogEntry } from '@/types'

const CATALOG_URL = '/api/openrouter/catalog'
const FAVORITES_URL = '/api/openrouter/favorites'

/** For the favorites picker — the full live OpenRouter catalog. */
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

/** Refresh the list of OpenRouter model ids exposed in node UI / Inspector model slots. */
export async function saveOpenRouterFavorites(ids: string[]): Promise<string[]> {
  const res = await fetch(FAVORITES_URL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  })
  if (!res.ok) throw new Error(`${FAVORITES_URL} ${res.status}`)
  return res.json()
}
