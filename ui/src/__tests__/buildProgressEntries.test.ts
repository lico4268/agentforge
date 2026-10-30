import { describe, expect, it } from 'vitest'
import { buildProgressEntries, deriveFlowStatuses } from '@/app/buildProgressEntries'
import type { ExecutionEvent } from '@/types'

function evt(partial: Partial<ExecutionEvent>): ExecutionEvent {
  return {
    eventType: 'node_start',
    runId: 'run-1',
    nodeId: 'reasoning',
    timestamp: new Date().toISOString(),
    ...partial,
  } as ExecutionEvent
}

describe('buildProgressEntries', () => {
  it('pairs node_start/node_end into one done entry', () => {
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'reasoning' }),
        evt({ eventType: 'node_end', nodeId: 'reasoning', durationMs: 500, output: 'ok' }),
      ],
      null,
    )
    expect(entries).toEqual([
      { nodeId: 'reasoning', status: 'done', durationMs: 500, output: 'ok' },
    ])
  })

  it('marks a node_end with policyDecision.activated=false as skipped', () => {
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'review' }),
        evt({
          eventType: 'node_end',
          nodeId: 'review',
          policyDecision: { activated: false, reason: 'not needed' },
        }),
      ],
      null,
    )
    expect(entries[0].status).toBe('skipped')
  })

  it('marks an error event as failed', () => {
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'reasoning' }),
        evt({ eventType: 'error', nodeId: 'reasoning', error: { type: 'ValueError', detail: 'bad' } }),
      ],
      null,
    )
    expect(entries[0].status).toBe('failed')
  })

  it('keeps a synthetic __guard_N node id as its own entry (not diagram-bound)', () => {
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: '__guard_1' }),
        evt({ eventType: 'node_end', nodeId: '__guard_1', durationMs: 10 }),
      ],
      null,
    )
    expect(entries).toHaveLength(1)
    expect(entries[0].nodeId).toBe('__guard_1')
  })

  it('appends a paused entry from pendingInterrupt, converting the running visit', () => {
    const entries = buildProgressEntries(
      [evt({ eventType: 'node_start', nodeId: 'checkpoint' })],
      { nodeId: 'checkpoint', payload: { summary: 's', fields: {}, actions: ['approve'] } },
    )
    expect(entries).toHaveLength(1)
    expect(entries[0].status).toBe('paused')
  })
})

describe('deriveFlowStatuses', () => {
  it('colors non-ASCII (Korean) node ids just like ASCII ones', () => {
    // Review finding 1: the old implementation tokenized the flow string with a regex (/[A-Za-z0-9_.:-]+/g),
    // which can't match non-ASCII node ids at all — the design spec §3.3 example itself
    // uses non-ASCII ids. Now architecture.nodes[].id is used directly.
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'input' }),
        evt({ eventType: 'node_start', nodeId: 'brouillon' }),
        evt({ eventType: 'node_end', nodeId: 'brouillon', durationMs: 100 }),
      ],
      null,
    )
    const statuses = deriveFlowStatuses(entries, ['input', 'brouillon', 'révision'])
    expect(statuses).toEqual({ input: 'running', brouillon: 'done' })
  })

  it('drops synthetic __guard_N ids even though architecture.nodes includes them', () => {
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'reasoning' }),
        evt({ eventType: 'node_start', nodeId: '__guard_1' }),
      ],
      null,
    )
    const statuses = deriveFlowStatuses(entries, ['reasoning', '__guard_1'])
    expect(statuses).toEqual({ reasoning: 'running' })
  })
})
