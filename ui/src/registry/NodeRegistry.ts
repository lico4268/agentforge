import type { ComponentType } from 'react'
import type { NodeProps } from '@xyflow/react'
import type { NodeManifest } from '@/types'

/**
 * The registry maps node `type` → manifest and → React component. React Flow's
 * `nodeTypes` is built *from* this, never hardcoded, so new nodes appear in the
 * palette and canvas with zero component changes. See ui-architecture.md §5.
 */
export class NodeRegistry {
  private manifests = new Map<string, NodeManifest>()
  private custom = new Map<string, ComponentType<NodeProps>>()

  constructor(manifests: NodeManifest[] = []) {
    this.setManifests(manifests)
  }

  setManifests(manifests: NodeManifest[]) {
    this.manifests.clear()
    for (const m of manifests) this.manifests.set(m.type, m)
  }

  /** Register a custom renderer that overrides GenericNode for one type. */
  registerComponent(type: string, component: ComponentType<NodeProps>) {
    this.custom.set(type, component)
  }

  get(type: string): NodeManifest | undefined {
    return this.manifests.get(type)
  }

  all(): NodeManifest[] {
    return [...this.manifests.values()]
  }

  customComponent(type: string): ComponentType<NodeProps> | undefined {
    return this.custom.get(type)
  }
}
