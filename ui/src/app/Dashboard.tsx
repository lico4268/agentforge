import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTransport } from '@/transport/TransportContext'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { loadArchFiles, loadArchFile } from '@/registry/loadArchFiles'
import { ArchGraphSchema } from '@/types/arch'
import { LogPanel } from '@/panels/LogPanel'
import { FlowDiagram } from './FlowDiagram'
import { NodeProgress } from './NodeProgress'
import { buildProgressEntries, deriveFlowStatuses } from './buildProgressEntries'

/**
 * Read-only dashboard — no authoring (canvas editing). Picking a file from the
 * arch.yaml list hands the already-parsed `flow` string from the server straight
 * to mermaid to get the diagram (zero layout code, design §3.2). Execution reuses
 * the existing WS transport/store as-is — Run and checkpoint approve/reject are
 * runtime actions, so the "authoring read-only" rule doesn't apply (task-6 brief GLOBAL CONSTRAINTS).
 */
export function Dashboard() {
  const transport = useTransport()
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [task, setTask] = useState('')

  const {
    data: archList,
    error: archListError,
  } = useQuery({
    queryKey: ['arch-list'],
    queryFn: loadArchFiles,
    staleTime: 60_000,
  })

  const activeName = selectedName ?? archList?.[0]?.name ?? null

  const {
    data: archFile,
    error: archError,
  } = useQuery({
    queryKey: ['arch-file', activeName],
    queryFn: () => loadArchFile(activeName!),
    enabled: activeName != null,
  })

  const events = useExecutionStore((s) => s.events)
  const runId = useExecutionStore((s) => s.runId)
  const runStatus = useExecutionStore((s) => s.runStatus)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const runError = useExecutionStore((s) => s.runError)
  const runResult = useExecutionStore((s) => s.runResult)
  const reset = useExecutionStore((s) => s.reset)

  const graph = archFile ? ArchGraphSchema.safeParse(archFile.architecture) : null
  const flow = graph?.success ? graph.data.flow : ''
  // Diagram colouring targets come only from the server-parsed architecture.nodes[].id
  // — re-tokenizing the flow string with a regex misses non-ASCII ids (e.g. Korean)
  // (review finding 1). Excluding __guard_N is deriveFlowStatuses' job.
  const nodeIds = graph?.success ? graph.data.nodes.map((n) => n.id) : []

  const entries = buildProgressEntries(events, pendingInterrupt)
  const statuses = deriveFlowStatuses(entries, nodeIds)

  const isBusy = runStatus === 'running' || runStatus === 'paused'

  const onRun = () => {
    if (!activeName) return
    reset()
    transport.send({
      kind: 'run',
      archFile: activeName,
      input: { task, task_tags: [] },
    })
  }

  const onResume = (decision: string) => {
    if (!runId || !pendingInterrupt) return
    transport.send({
      kind: 'resume',
      runId,
      nodeId: pendingInterrupt.nodeId,
      decision: { action: decision as 'approve' | 'revise' | 'reject' },
    })
  }

  return (
    <div className="flex h-screen flex-col gap-3 overflow-auto bg-[#09100c] p-4 text-[13px] text-[#dde4dd]">
      <header className="flex shrink-0 items-center gap-2">
        <span className="text-[15px] font-semibold tracking-tight">Agentforge</span>
        <select
          value={activeName ?? ''}
          onChange={(e) => setSelectedName(e.target.value)}
          className="rounded border border-[#3c4a42] bg-[#242c27] px-2 py-1"
        >
          {!archList && (
            <option value="">{archListError ? 'Failed to load' : 'Loading…'}</option>
          )}
          {archList?.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="task input"
          className="flex-1 rounded border border-[#3c4a42] bg-[#242c27] px-2 py-1"
        />
        <button
          type="button"
          onClick={onRun}
          disabled={!activeName || isBusy}
          className="rounded bg-[#4edea3] px-4 py-1.5 font-bold text-[#003824] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {runStatus === 'paused' ? 'Waiting for review…' : runStatus === 'running' ? 'Running…' : 'Run'}
        </button>
      </header>

      {archListError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          Failed to load arch file list: {(archListError as Error).message}
        </div>
      )}

      {archList && archList.length === 0 && (
        <div className="shrink-0 rounded border border-[#3c4a42] px-3 py-2 text-[#86948a]">
          No arch files found in server/arch/.
        </div>
      )}

      {archError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          {(archError as Error).message}
        </div>
      )}

      {archFile && archFile.warnings.length > 0 && (
        <ul className="shrink-0 rounded border border-[#ffd180]/50 bg-[#ffd180]/10 px-3 py-2 text-[#ffd180]">
          {archFile.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}

      {/* Placed after the file-load banner (above) and just above the diagram/progress list (below) —
          "what was run and why it failed" is an execution result, so it belongs right before
          where that result is shown. Even if it appears together with a file-load error, they
          stack vertically without overlapping (no competition). It reads the store's runError directly,
          so reset()/the next run_started (both set runError back to null)
          clear it automatically — no separate dismiss logic. */}
      {runError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          {runError}
        </div>
      )}

      {/* If the final answer can't be seen anywhere on screen after a run (previously it was only
          visible by expanding the last node), the tool is incomplete as an agent pipeline runner
          — a separate issue from minimalism (BLOCKING 3). runResult is the run_complete WS
          message as-is, so reset()/the next run start clears it automatically. */}
      {runResult && (
        <div className="shrink-0 rounded border border-[#4edea3]/50 bg-[#4edea3]/10 px-3 py-2 text-[#dde4dd]">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
            Result
          </div>
          <div className="whitespace-pre-wrap">{String(runResult.answer ?? '(no answer)')}</div>
        </div>
      )}

      {flow && <FlowDiagram flow={flow} statuses={statuses} />}

      <div className="min-h-0 flex-1 overflow-auto">
        <NodeProgress entries={entries} onResume={onResume} />
      </div>

      {/* Run log + run artifacts (per-node .md from server/workspace.py, token usage)
          viewer — it disappeared from the screen when Task 7 deleted Layout.tsx, the only
          place that rendered it (BLOCKING 3). Prevents workspace.py/REST from becoming dead code. */}
      <div className="h-64 shrink-0 overflow-hidden rounded border border-[#3c4a42]/50">
        <LogPanel />
      </div>
    </div>
  )
}
