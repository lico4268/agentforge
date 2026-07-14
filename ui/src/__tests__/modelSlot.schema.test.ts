import { describe, it, expect } from 'vitest'
import { ModelSlotSchema, TokenUsageSchema } from '@/types'

describe('ModelSlotSchema', () => {
  it('구형 슬롯(temperature/role만)을 하위호환으로 파싱한다', () => {
    const old = {
      id: 'slot-1',
      provider: 'google',
      model: 'gemini-3.1-flash-lite',
      temperature: 0,
      role: '',
    }
    const s = ModelSlotSchema.parse(old)
    expect(s.maxTokens).toBeUndefined()
    expect(s.topP).toBeUndefined()
    expect(s.stopSequences).toBeUndefined()
    expect(s.seed).toBeUndefined()
    expect(s.timeoutSeconds).toBeUndefined()
    expect(s.retryCount).toBeUndefined()
    expect(s.fallback).toBeUndefined()
  })

  it('전체 override 필드를 보존한다', () => {
    const full = {
      id: 'slot-2',
      provider: 'openai',
      model: 'gpt-4o',
      temperature: 0.4,
      maxTokens: 1024,
      topP: 0.9,
      stopSequences: ['END', 'STOP'],
      seed: 42,
      timeoutSeconds: 60,
      retryCount: 3,
      fallback: { provider: 'google', model: 'gemini-3.5-flash', temperature: 0 },
    }
    const s = ModelSlotSchema.parse(full)
    expect(s.maxTokens).toBe(1024)
    expect(s.topP).toBe(0.9)
    expect(s.stopSequences).toEqual(['END', 'STOP'])
    expect(s.seed).toBe(42)
    expect(s.timeoutSeconds).toBe(60)
    expect(s.retryCount).toBe(3)
    expect(s.fallback?.model).toBe('gemini-3.5-flash')
  })

  it('fallback: null 을 허용한다', () => {
    const s = ModelSlotSchema.parse({
      id: 'slot-3',
      provider: 'google',
      model: 'gemini-3.1-flash-lite',
      temperature: 0,
      fallback: null,
    })
    expect(s.fallback).toBeNull()
  })
})

describe('TokenUsageSchema', () => {
  it('관측 메타(model/attempt/fallbackUsed)를 보존한다', () => {
    const tu = TokenUsageSchema.parse({
      prompt: 100,
      completion: 20,
      model: 'gpt-4o',
      attempt: 1,
      fallbackUsed: true,
    })
    expect(tu.model).toBe('gpt-4o')
    expect(tu.attempt).toBe(1)
    expect(tu.fallbackUsed).toBe(true)
  })

  it('최소(prompt/completion) 페이로드도 파싱한다', () => {
    const tu = TokenUsageSchema.parse({ prompt: 5, completion: 3 })
    expect(tu.prompt).toBe(5)
    expect(tu.model).toBeUndefined()
  })
})
