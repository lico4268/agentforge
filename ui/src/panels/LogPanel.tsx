import { useRef, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { Markdown } from '@/panels/Markdown'
import { loadRunFiles, loadRunFileContent } from '@/registry/loadRunFiles'

type Tab = 'log' | 'files'

export function LogPanel() {
  const events = useExecutionStore((s) => s.events)
  const runId = useExecutionStore((s) => s.runId)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [tab, setTab] = useState<Tab>('log')

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length])

  return (
    <div className="flex h-full flex-col bg-[#09100c]">
      {/* Header with tabs */}
      <div className="flex shrink-0 items-center gap-2 border-b border-[#3c4a42]/50 px-4 py-2">
        <TabButton active={tab === 'log'} onClick={() => setTab('log')} icon="terminal" label="Log" />
        <TabButton active={tab === 'files'} onClick={() => setTab('files')} icon="folder" label="Files" />
        {tab === 'log' && events.length > 0 && (
          <span className="ml-auto font-mono text-[10px] text-[#3c4a42]">
            {events.length} events
          </span>
        )}
      </div>

      {/* Content */}
      {tab === 'log' ? (
        <EventLog events={events} scrollRef={scrollRef} />
      ) : (
        <FilesView runId={runId} />
      )}
    </div>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: string
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-widest transition-colors ${
        active
          ? 'bg-[#2f3632] text-[#4edea3]'
          : 'text-[#86948a] hover:text-[#bbcabf]'
      }`}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 12 }}>{icon}</span>
      {label}
    </button>
  )
}

function EventLog({
  events,
  scrollRef,
}: {
  events: ReturnType<typeof useExecutionStore.getState>['events']
  scrollRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
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
            {e.error && (
              <span className="text-[#ff8a80]">
                {e.error.type}: {e.error.detail}
              </span>
            )}
          </div>
        ))
      )}
    </div>
  )
}

function FilesView({ runId }: { runId: string | null }) {
  const [selectedFile, setSelectedFile] = useState<string | null>(null)

  const { data: files, isLoading: filesLoading, error: filesError } = useQuery({
    queryKey: ['run-files', runId],
    queryFn: () => loadRunFiles(runId!),
    enabled: !!runId,
    staleTime: 5_000,
    retry: 1,
  })

  const { data: fileContent, isLoading: contentLoading } = useQuery({
    queryKey: ['run-file-content', runId, selectedFile],
    queryFn: () => loadRunFileContent(runId!, selectedFile!),
    enabled: !!runId && !!selectedFile,
    staleTime: 30_000,
    retry: 1,
  })

  if (!runId) {
    return (
      <div className="flex flex-1 items-center justify-center font-mono text-[11px] text-[#3c4a42]">
        No run yet — press Run to generate workspace files.
      </div>
    )
  }

  if (filesLoading) {
    return <div className="py-2 font-mono text-[11px] text-[#3c4a42]">Loading files…</div>
  }

  if (filesError) {
    return (
      <div className="py-2 font-mono text-[11px] text-[#ff8a80]">
        Error: {filesError.message}
      </div>
    )
  }

  if (!files || files.length === 0) {
    return (
      <div className="py-2 font-mono text-[11px] text-[#3c4a42]">
        No files yet — run an architecture to generate node outputs.
      </div>
    )
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* File list */}
      <div className="w-48 shrink-0 overflow-y-auto border-r border-[#3c4a42]/50">
        {files.map((f) => (
          <button
            key={f.name}
            onClick={() => setSelectedFile(f.name)}
            className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors ${
              selectedFile === f.name
                ? 'bg-[#2f3632] text-[#4edea3]'
                : 'text-[#bbcabf] hover:bg-[#161d19]'
            }`}
          >
            <span className="font-mono text-[11px] truncate">{f.nodeId}</span>
            <span className="font-mono text-[9px] text-[#3c4a42]">
              {formatBytes(f.sizeBytes)}
            </span>
          </button>
        ))}
      </div>

      {/* File content */}
      <div className="flex-1 overflow-y-auto p-3">
        {!selectedFile ? (
          <div className="font-mono text-[11px] text-[#3c4a42]">Select a file to view.</div>
        ) : contentLoading ? (
          <div className="font-mono text-[11px] text-[#3c4a42]">Loading…</div>
        ) : fileContent ? (
          <Markdown>{fileContent.content}</Markdown>
        ) : null}
      </div>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function eventColor(type: string) {
  switch (type) {
    case 'node_start': return 'text-[#ffd180]'
    case 'node_end':   return 'text-[#4edea3]'
    case 'error':      return 'text-[#ff8a80]'
    default:           return 'text-[#86948a]'
  }
}