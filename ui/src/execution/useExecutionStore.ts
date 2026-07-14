import { create } from 'zustand'
import type { ExecutionEvent, NodeRuntime } from '@/types'
import { reduceEvent } from './eventReducer'

/**
 * Execution store — high-frequency runtime state from the backend event stream.
 * Kept apart from the topology store. Nodes subscribe to *their own* nodeId via
 * a selector, so an event re-renders only that node. See ui-architecture.md §2/§6.
 */
type RunStatus = 'idle' | 'running' | 'paused' | 'complete' | 'error'

type RunMeta = {
  runId: string | null
  status: RunStatus
  result: Record<string, unknown> | null
  error?: string
}

export type PendingInterrupt = {
  nodeId: string
  payload: {
    summary: string
    fields: Record<string, unknown>
    actions: ('approve' | 'revise' | 'reject')[]
  }
}

type ExecutionState = {
  runId: string | null
  activeNodeId: string | null
  runtimeByNodeId: Record<string, NodeRuntime>
  events: ExecutionEvent[]
  runStatus: RunStatus
  runResult: Record<string, unknown> | null
  runError: string | null
  pendingInterrupt: PendingInterrupt | null

  applyEvent: (event: ExecutionEvent) => void
  setRunState: (meta: RunMeta) => void
  setInterrupt: (runId: string, nodeId: string, payload: PendingInterrupt['payload']) => void
  reset: () => void
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  runId: null,
  activeNodeId: null,
  runtimeByNodeId: {},
  events: [],
  runStatus: 'idle',
  runResult: null,
  runError: null,
  pendingInterrupt: null,

  applyEvent: (event) =>
    set((s) => ({
      runId: event.runId,
      activeNodeId:
        event.eventType === 'node_start' ? event.nodeId : s.activeNodeId,
      runtimeByNodeId: {
        ...s.runtimeByNodeId,
        [event.nodeId]: reduceEvent(s.runtimeByNodeId[event.nodeId], event),
      },
      events: [...s.events, event],
    })),

  setRunState: ({ runId, status, result, error }) =>
    set((s) => ({
      runId: runId ?? s.runId,
      runStatus: status,
      runResult: result,
      runError: error ?? null,
      pendingInterrupt: status === 'complete' || status === 'error' ? null : s.pendingInterrupt,
      activeNodeId: status === 'complete' || status === 'error' ? null : s.activeNodeId,
    })),

  setInterrupt: (runId, nodeId, payload) =>
    set({
      runId,
      runStatus: 'paused',
      activeNodeId: nodeId,
      pendingInterrupt: { nodeId, payload },
    }),

  reset: () =>
    set({
      runId: null,
      activeNodeId: null,
      runtimeByNodeId: {},
      events: [],
      runStatus: 'idle',
      runResult: null,
      runError: null,
      pendingInterrupt: null,
    }),
}))

/** Selector hook: subscribe to a single node's runtime (re-render isolation). */
export const useNodeRuntime = (nodeId: string) =>
  useExecutionStore((s) => s.runtimeByNodeId[nodeId])
