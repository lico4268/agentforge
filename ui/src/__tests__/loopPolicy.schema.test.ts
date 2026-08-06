import { describe, it, expect } from 'vitest'
import { LoopPolicySchema, ArchitectureSchema } from '@/types'

describe('LoopPolicySchema', () => {
  it('유효한 LoopPolicy를 통과시킨다', () => {
    const policy = {
      id: 'loop-1',
      kind: 'critiqueRevise',
      feedbackEdgeIds: ['e-review-reasoning'],
      memberNodeIds: ['reasoning', 'review'],
      exitEdgeIds: ['e-review-output'],
      guard: { maxIterations: 3, stuck: { window: 3, threshold: 1 } },
      onExhaustion: 'exit',
    }
    const parsed = LoopPolicySchema.parse(policy)
    expect(parsed.guard.maxIterations).toBe(3)
    expect(parsed.guard.stuck?.window).toBe(3)
  })

  it('알 수 없는 kind는 거부한다 (v1은 retry 미지원)', () => {
    const bad = {
      id: 'loop-1',
      kind: 'retry',
      feedbackEdgeIds: [],
      memberNodeIds: [],
      exitEdgeIds: [],
      guard: {},
      onExhaustion: 'exit',
    }
    expect(() => LoopPolicySchema.parse(bad)).toThrow()
  })

  it('알 수 없는 onExhaustion은 거부한다', () => {
    const bad = {
      id: 'loop-1',
      kind: 'critiqueRevise',
      feedbackEdgeIds: [],
      memberNodeIds: [],
      exitEdgeIds: [],
      guard: {},
      onExhaustion: 'retry-forever',
    }
    expect(() => LoopPolicySchema.parse(bad)).toThrow()
  })
})

describe('ArchitectureSchema loopPolicies migration', () => {
  it('loopPolicies 키가 없는 기존 Architecture를 빈 배열로 채운다', () => {
    const legacy = {
      version: '0.1',
      metadata: { name: 'legacy', createdAt: '2026-01-01T00:00:00.000Z' },
      nodes: [],
      edges: [],
    }
    const parsed = ArchitectureSchema.parse(legacy)
    expect(parsed.loopPolicies).toEqual([])
  })
})
