import type { ExecutionEvent } from '@/types'
import type { PendingInterrupt } from '@/execution/useExecutionStore'
import type { ProgressEntry } from './NodeProgress'

/**
 * Folds the execution event stream (the store's `events`, in arrival order) into the visit
 * list that `NodeProgress` draws. Each `node_start` for the same nodeId opens a new entry
 * — that's what gives NodeProgress's #1/#2 revisit numbering its meaning.
 *
 * A loop's synthetic guard node (`__guard_N`) is treated like any other node — it isn't in the
 * flow string/diagram, but its events really do arrive (design decision, see task-6 brief).
 * It is filtered out only for diagram colouring (`deriveFlowStatuses`).
 */
export function buildProgressEntries(
  events: ExecutionEvent[],
  pendingInterrupt: PendingInterrupt | null,
): ProgressEntry[] {
  const entries: ProgressEntry[] = []

  for (const event of events) {
    if (event.eventType === 'node_start') {
      entries.push({ nodeId: event.nodeId, status: 'running', durationMs: null, output: null })
      continue
    }
    const idx = findLastRunning(entries, event.nodeId)
    if (idx === -1) continue

    if (event.eventType === 'node_end') {
      const skipped = event.policyDecision?.activated === false
      entries[idx] = {
        ...entries[idx],
        status: skipped ? 'skipped' : 'done',
        durationMs: event.durationMs ?? null,
        output: event.output ?? null,
      }
    } else if (event.eventType === 'error') {
      entries[idx] = {
        ...entries[idx],
        status: 'failed',
        output: event.error ?? null,
      }
    }
  }

  if (pendingInterrupt) {
    const idx = findLastRunning(entries, pendingInterrupt.nodeId)
    const paused: ProgressEntry = {
      nodeId: pendingInterrupt.nodeId,
      status: 'paused',
      durationMs: null,
      output: pendingInterrupt.payload,
    }
    if (idx === -1) entries.push(paused)
    else entries[idx] = paused
  }

  return entries
}

function findLastRunning(entries: ProgressEntry[], nodeId: string): number {
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].nodeId === nodeId && entries[i].status === 'running') return i
  }
  return -1
}

/**
 * The status map to pass to FlowDiagram — keeps only nodeIds that actually appear in `nodeIds`
 * (the backend's `architecture.nodes[].id`, the authoritative list).
 *
 * The old implementation tokenized the `flow` mermaid string with a regex to decide membership,
 * but when a node name contained non-ASCII characters (e.g. Korean; the design spec §3.3 example
 * itself uses non-ASCII names) the token regex missed those characters entirely and diagram colouring
 * silently failed (review finding 1). `architecture.nodes` is the authoritative id list already
 * parsed by the server, so no re-parsing is needed — using it directly eliminates this whole class of problem.
 *
 * `__guard_N` (loop synthetic guard) is in `architecture.nodes` but not in the flow string/
 * diagram, so it is filtered out here (so mermaid's `class` directive doesn't implicitly
 * create the undeclared node and add a stray box to the picture).
 */
export function deriveFlowStatuses(
  entries: ProgressEntry[],
  nodeIds: Iterable<string>,
): Record<string, 'running' | 'done' | 'failed'> {
  const valid = new Set(Array.from(nodeIds).filter((id) => !id.startsWith('__guard_')))
  const out: Record<string, 'running' | 'done' | 'failed'> = {}
  for (const e of entries) {
    if ((e.status === 'running' || e.status === 'done' || e.status === 'failed') && valid.has(e.nodeId)) {
      out[e.nodeId] = e.status
    }
  }
  return out
}
