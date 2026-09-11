import { describe, it, expect } from 'vitest'
import { TokenUsageSchema } from '@/types'

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
