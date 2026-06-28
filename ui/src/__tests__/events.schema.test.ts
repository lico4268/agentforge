import { describe, it, expect } from 'vitest'
import { ExecutionEventSchema } from '@/types/events'

// 백엔드 events.py to_frontend()가 보내는 camelCase 페이로드와의 계약 검증.
describe('ExecutionEventSchema', () => {
  it('백엔드 node_start 이벤트(최소 필드)를 통과시킨다', () => {
    const payload = {
      eventType: 'node_start',
      runId: 'run-1',
      nodeId: 'reasoning',
      timestamp: new Date().toISOString(),
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.nodeId).toBe('reasoning')
  })

  it('policyDecision/tokenUsage 등 선택 필드를 보존한다', () => {
    const payload = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: 'review_policy',
      timestamp: new Date().toISOString(),
      durationMs: 42,
      policyDecision: { activated: true, reason: 'high-stakes tag' },
      tokenUsage: { prompt: 100, completion: 20 },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.policyDecision?.activated).toBe(true)
    expect(parsed.tokenUsage?.prompt).toBe(100)
  })

  it('알 수 없는 eventType은 거부한다', () => {
    const bad = {
      eventType: 'not_a_real_event',
      runId: 'run-1',
      nodeId: 'x',
      timestamp: new Date().toISOString(),
    }
    expect(() => ExecutionEventSchema.parse(bad)).toThrow()
  })
})
