import { useState, type DragEvent } from 'react'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META, NODE_TYPE_ICONS } from '@/lib/categoryStyle'
import { NODE_CATEGORIES, type NodeCategory, type NodeManifest } from '@/types'
import { DRAG_MIME } from '@/canvas/dragTypes'

export function NodeLibrary() {
  const registry = useRegistry()
  const byCategory = groupByCategory(registry.all())
  const [expanded, setExpanded] = useState<Set<NodeCategory>>(new Set(['cognitive', 'model', 'policy', 'io']))

  const toggle = (cat: NodeCategory) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      return next
    })

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#161d19]/80 backdrop-blur-xl">
      <div className="border-b border-[#3c4a42]/50 px-4 py-3">
        <h2 className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#86948a]">
          Node Library
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {NODE_CATEGORIES.map((cat) => {
          const items = byCategory[cat]
          if (!items?.length) return null
          const meta = CATEGORY_META[cat]
          const isOpen = expanded.has(cat)

          return (
            <div key={cat}>
              {/* Category header */}
              <button
                onClick={() => toggle(cat)}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-[#242c27] group"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{
                    background: meta.color,
                    boxShadow: isOpen ? `0 0 6px ${meta.color}66` : 'none',
                  }}
                />
                <span className="flex-1 text-[13px] font-semibold text-[#dde4dd]">{meta.label}</span>
                <span
                  className="material-symbols-outlined text-[#86948a] transition-transform group-hover:text-[#bbcabf]"
                  style={{ fontSize: 16, transform: isOpen ? 'rotate(0deg)' : 'rotate(-90deg)', transition: 'transform 0.15s ease' }}
                >
                  expand_more
                </span>
              </button>

              {/* Node cards */}
              {isOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-1 pb-2">
                  {items.map((m) => (
                    <LibraryCard key={m.type} manifest={m} color={meta.color} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LibraryCard({ manifest, color }: { manifest: NodeManifest; color: string }) {
  const icon = NODE_TYPE_ICONS[manifest.type] ?? CATEGORY_META[manifest.category]?.icon ?? 'widgets'

  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData(DRAG_MIME, manifest.type)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      title={manifest.description}
      className="group cursor-grab rounded-md border border-[rgba(255,255,255,0.06)] bg-[#161d19]/50 p-2.5 transition-all active:cursor-grabbing hover:border-[rgba(255,255,255,0.14)] hover:bg-[#1a211d]"
      style={{
        borderLeft: `3px solid ${color}`,
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLElement).style.boxShadow = `0 0 12px -2px ${color}55`
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLElement).style.boxShadow = 'none'
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="material-symbols-outlined shrink-0"
          style={{ fontSize: 15, color }}
        >
          {icon}
        </span>
        <span className="text-[13px] font-medium text-[#dde4dd]">{manifest.label}</span>
      </div>
      {manifest.description && (
        <p className="mt-0.5 text-[11px] leading-tight text-[#86948a] opacity-80">
          {manifest.description}
        </p>
      )}
    </div>
  )
}

function groupByCategory(manifests: NodeManifest[]) {
  const out = {} as Record<NodeCategory, NodeManifest[]>
  for (const m of manifests) (out[m.category] ??= []).push(m)
  return out
}
