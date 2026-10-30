import { describe, it, expect } from 'vitest'
import { ExecutionEventSchema } from '@/types/events'

// Contract check against the camelCase payload sent by the backend's events.py to_frontend().
describe('ExecutionEventSchema', () => {
  it('accepts a backend node_start event (minimal fields)', () => {
    const payload = {
      eventType: 'node_start',
      runId: 'run-1',
      nodeId: 'reasoning',
      timestamp: new Date().toISOString(),
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.nodeId).toBe('reasoning')
  })

  it('preserves optional fields such as policyDecision/tokenUsage', () => {
    const payload = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: 'review',
      timestamp: new Date().toISOString(),
      durationMs: 42,
      policyDecision: { activated: true, reason: 'high-stakes tag', branch: 'clarify' },
      tokenUsage: { prompt: 100, completion: 20 },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.policyDecision?.activated).toBe(true)
    expect(parsed.tokenUsage?.prompt).toBe(100)
  })

  it('accepts an error event with a structured error field', () => {
    const payload = {
      eventType: 'error',
      runId: 'run-1',
      nodeId: 'reasoning',
      timestamp: new Date().toISOString(),
      message: 'bad output',
      error: { type: 'ValueError', detail: 'bad output' },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.error?.type).toBe('ValueError')
    expect(parsed.error?.detail).toBe('bad output')
  })

  it('rejects an unknown eventType', () => {
    const bad = {
      eventType: 'not_a_real_event',
      runId: 'run-1',
      nodeId: 'x',
      timestamp: new Date().toISOString(),
    }
    expect(() => ExecutionEventSchema.parse(bad)).toThrow()
  })

  it('preserves the loopRuntime field (loopNodeId = actual canvas node id)', () => {
    const payload = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: 'loop_guard',
      timestamp: new Date().toISOString(),
      loopRuntime: {
        loopNodeId: 'loop_guard',
        iteration: 2,
        maxIterations: 5,
        exitReason: 'maxIterations',
      },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.loopRuntime?.loopNodeId).toBe('loop_guard')
    expect(parsed.loopRuntime?.exitReason).toBe('maxIterations')
  })

  it('rejects a legacy payload that only has loopPolicyId', () => {
    const legacy = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: '__loop_guard__loop-1',
      timestamp: new Date().toISOString(),
      loopRuntime: { loopPolicyId: 'loop-1', iteration: 1 },
    }
    expect(() => ExecutionEventSchema.parse(legacy)).toThrow()
  })

  it('accepts an event without loopRuntime (optional field)', () => {
    const payload = {
      eventType: 'node_start',
      runId: 'run-1',
      nodeId: 'reasoning',
      timestamp: new Date().toISOString(),
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.loopRuntime).toBeUndefined()
  })
})
