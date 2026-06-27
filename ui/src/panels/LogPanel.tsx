import { useExecutionStore } from '@/execution/useExecutionStore'

/**
 * Bottom log — the raw execution event stream. This is the v0.1 deliverable in
 * UI form: "which node ran/skipped and why". See ui-architecture.md §8.
 */
export function LogPanel() {
  const events = useExecutionStore((s) => s.events)

  return (
    <div className="flex h-full flex-col bg-[#0a0d14]">
      <div className="border-b border-white/5 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Execution Log
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px]">
        {events.length === 0 ? (
          <div className="text-slate-600">No events yet — press Run.</div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex gap-2 py-0.5">
              <span className="text-slate-600">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className={eventColor(e.eventType)}>{e.eventType}</span>
              <span className="text-slate-300">{e.nodeId}</span>
              {e.policyDecision && (
                <span className="text-amber-400">
                  [{e.policyDecision.activated ? 'activate' : 'skip'}: {e.policyDecision.reason}]
                </span>
              )}
              {e.durationMs != null && (
                <span className="text-slate-600">{e.durationMs}ms</span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function eventColor(type: string) {
  switch (type) {
    case 'node_start':
      return 'text-yellow-400'
    case 'node_end':
      return 'text-emerald-400'
    case 'error':
      return 'text-red-400'
    default:
      return 'text-slate-400'
  }
}
