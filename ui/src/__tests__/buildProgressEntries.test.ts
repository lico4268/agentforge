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
    // 리뷰 finding 1: 옛 구현은 flow 문자열을 정규식(/[A-Za-z0-9_.:-]+/g)으로
    // 토큰화했는데, 이건 한글 노드 id를 아예 못 잡는다 — 설계 스펙 §3.3의 예시
    // 자체가 초안/검토/재작성이다. 이제는 architecture.nodes[].id를 그대로 쓴다.
    const entries = buildProgressEntries(
      [
        evt({ eventType: 'node_start', nodeId: 'input' }),
        evt({ eventType: 'node_start', nodeId: '초안' }),
        evt({ eventType: 'node_end', nodeId: '초안', durationMs: 100 }),
      ],
      null,
    )
    const statuses = deriveFlowStatuses(entries, ['input', '초안', '검토'])
    expect(statuses).toEqual({ input: 'running', 초안: 'done' })
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
