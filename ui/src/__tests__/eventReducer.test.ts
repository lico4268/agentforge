import { describe, it, expect } from 'vitest'
import { reduceEvent } from '@/execution/eventReducer'
import { EMPTY_RUNTIME, type ExecutionEvent } from '@/types'

function evt(partial: Partial<ExecutionEvent>): ExecutionEvent {
  return {
    eventType: 'node_start',
    runId: 'run-1',
    nodeId: 'reasoning',
    timestamp: new Date().toISOString(),
    ...partial,
  } as ExecutionEvent
}

describe('reduceEvent', () => {
  it('node_start → running', () => {
    const next = reduceEvent(undefined, evt({ eventType: 'node_start' }))
    expect(next.status).toBe('running')
  })

  it('error → failed 이며 lastError를 보존한다', () => {
    const next = reduceEvent(
      EMPTY_RUNTIME,
      evt({ eventType: 'error', error: { type: 'ValueError', detail: 'bad output' } }),
    )
    expect(next.status).toBe('failed')
    expect(next.lastError).toEqual({ type: 'ValueError', detail: 'bad output' })
  })
})
