import { useGraphStore } from '@/stores/useGraphStore'
import { useNodeRuntime } from '@/execution/useExecutionStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import type { ConfigField } from '@/types'

/**
 * Right panel — config form generated from the selected node's manifest, plus
 * its last input/output once a run has touched it. See ui-architecture.md §3/§10.
 */
export function Inspector() {
  const registry = useRegistry()
  const selectedId = useGraphStore((s) => s.selectedNodeId)
  const node = useGraphStore((s) => s.nodes.find((n) => n.id === s.selectedNodeId))
  const updateNodeConfig = useGraphStore((s) => s.updateNodeConfig)
  const runtime = useNodeRuntime(selectedId ?? '')

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0d111a] p-4 text-center text-xs text-slate-600">
        Select a node to inspect its config and I/O.
      </div>
    )
  }

  const manifest = registry.get(node.data.manifestType)
  if (!manifest) return null
  const meta = CATEGORY_META[manifest.category]
  const config = node.data.config

  const setField = (key: string, value: unknown) =>
    updateNodeConfig(node.id, { ...config, [key]: value })

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#0d111a] p-3 text-sm">
      <div className="mb-1 flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: meta.color }} />
        <h2 className="font-semibold text-slate-100">{manifest.label}</h2>
      </div>
      <p className="mb-4 text-xs text-slate-500">{manifest.description}</p>

      {manifest.config.length > 0 && (
        <div className="mb-4 flex flex-col gap-3">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Config
          </h3>
          {manifest.config.map((field) => (
            <Field
              key={field.key}
              field={field}
              value={config[field.key] ?? field.default}
              onChange={(v) => setField(field.key, v)}
            />
          ))}
        </div>
      )}

      {runtime && runtime.callCount > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Last run
          </h3>
          <Stat label="Status" value={runtime.status} />
          <Stat label="Calls" value={String(runtime.callCount)} />
          <Stat label="Duration" value={`${runtime.totalDurationMs} ms`} />
          <Stat label="Tokens" value={String(runtime.totalTokens)} />
          {runtime.policyDecision && (
            <Stat
              label="Policy"
              value={`${runtime.policyDecision.activated ? 'activated' : 'skipped'} — ${runtime.policyDecision.reason}`}
            />
          )}
          <IOBlock label="Output" value={runtime.lastOutput} />
        </div>
      )}
    </div>
  )
}

function Field({
  field,
  value,
  onChange,
}: {
  field: ConfigField
  value: unknown
  onChange: (v: unknown) => void
}) {
  const inputCls =
    'w-full rounded border border-white/10 bg-[#11151f] px-2 py-1 text-xs text-slate-100 outline-none focus:border-white/30'
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-slate-400">{field.label}</span>
      {field.type === 'select' ? (
        <select className={inputCls} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : field.type === 'text' ? (
        <textarea className={inputCls} rows={3} value={String(value ?? '')} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : field.type === 'boolean' ? (
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
      ) : field.type === 'number' ? (
        <input type="number" className={inputCls} value={Number(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))} />
      ) : (
        <input type="text" className={inputCls} value={String(value ?? '')} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="text-right text-slate-300">{value}</span>
    </div>
  )
}

function IOBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined) return null
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] text-slate-500">{label}</span>
      <pre className="overflow-x-auto rounded bg-black/40 p-2 text-[10px] text-slate-300">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}
