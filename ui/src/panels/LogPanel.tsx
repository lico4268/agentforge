import { useRef, useEffect } from 'react'
import { useExecutionStore } from '@/execution/useExecutionStore'

export function LogPanel() {
  const events     = useExecutionStore((s) => s.events)
  const scrollRef  = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length])

  return (
    <div className="flex h-full flex-col bg-[#09100c]">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-2 border-b border-[#3c4a42]/50 px-4 py-2">
        <span className="material-symbols-outlined text-[#86948a]" style={{ fontSize: 14 }}>terminal</span>
        <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#86948a]">
          Execution Log
        </span>
        {events.length > 0 && (
          <span className="ml-auto font-mono text-[10px] text-[#3c4a42]">
            {events.length} events
          </span>
        )}
      </div>

      {/* Event stream */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-2">
        {events.length === 0 ? (
          <div className="py-2 font-mono text-[11px] text-[#3c4a42]">
            No events yet — press Run.
          </div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex gap-3 py-0.5 font-mono text-[11px]">
              <span className="shrink-0 text-[#3c4a42]">
                {new Date(e.timestamp).toLocaleTimeString('en', { hour12: false })}
              </span>
              <span className={eventColor(e.eventType)}>{e.eventType}</span>
              <span className="text-[#bbcabf]">{e.nodeId}</span>
              {e.policyDecision && (
                <span className="text-[#ffd180]">
                  [{e.policyDecision.activated ? 'activate' : 'skip'}: {e.policyDecision.reason}]
                </span>
              )}
              {e.durationMs != null && (
                <span className="text-[#3c4a42]">{e.durationMs}ms</span>
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
    case 'node_start': return 'text-[#ffd180]'
    case 'node_end':   return 'text-[#4edea3]'
    case 'error':      return 'text-[#ff8a80]'
    default:           return 'text-[#86948a]'
  }
}
