import { describe, it, expect } from 'vitest'
import { TokenUsageSchema } from '@/types'

describe('TokenUsageSchema', () => {
  it('preserves observation metadata (model/attempt/fallbackUsed)', () => {
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

  it('also parses a minimal (prompt/completion) payload', () => {
    const tu = TokenUsageSchema.parse({ prompt: 5, completion: 3 })
    expect(tu.prompt).toBe(5)
    expect(tu.model).toBeUndefined()
  })
})
