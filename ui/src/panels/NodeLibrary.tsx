import type { DragEvent } from 'react'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { NODE_CATEGORIES, type NodeCategory, type NodeManifest } from '@/types'
import { DRAG_MIME } from '@/canvas/dragTypes'

/** Left palette — drag a node type onto the canvas to instantiate it. */
export function NodeLibrary() {
  const registry = useRegistry()
  const byCategory = groupByCategory(registry.all())

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#0d111a] p-3 text-sm">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Node Library
      </h2>
      {NODE_CATEGORIES.map((cat) => {
        const items = byCategory[cat]
        if (!items?.length) return null
        const meta = CATEGORY_META[cat]
        return (
          <div key={cat} className="mb-4">
            <div className="mb-1.5 flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: meta.color }}
              />
              <span className="text-[11px] font-medium text-slate-400">
                {meta.label}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {items.map((m) => (
                <LibraryItem key={m.type} manifest={m} color={meta.color} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function LibraryItem({ manifest, color }: { manifest: NodeManifest; color: string }) {
  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData(DRAG_MIME, manifest.type)
    e.dataTransfer.effectAllowed = 'move'
  }
  return (
    <div
      draggable
      onDragStart={onDragStart}
      title={manifest.description}
      className="cursor-grab rounded-md border border-white/5 bg-[#11151f] px-2.5 py-1.5 text-xs text-slate-200 hover:border-white/20 active:cursor-grabbing"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      {manifest.label}
    </div>
  )
}

function groupByCategory(manifests: NodeManifest[]) {
  const out = {} as Record<NodeCategory, NodeManifest[]>
  for (const m of manifests) (out[m.category] ??= []).push(m)
  return out
}
