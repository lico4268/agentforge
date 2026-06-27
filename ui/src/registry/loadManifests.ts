import { NodeManifestListSchema, type NodeManifest } from '@/types'
import { BUILTIN_MANIFESTS } from './builtinManifests'

const REGISTRY_URL = '/api/nodes'

/**
 * Loads the node registry. Tries the backend; falls back to the bundled set so
 * the editor works fully offline. See ui-architecture.md §5.
 */
export async function loadManifests(): Promise<NodeManifest[]> {
  try {
    const res = await fetch(REGISTRY_URL)
    if (!res.ok) throw new Error(`registry ${res.status}`)
    return NodeManifestListSchema.parse(await res.json())
  } catch {
    return BUILTIN_MANIFESTS
  }
}
