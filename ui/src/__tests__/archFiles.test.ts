import { describe, expect, it } from 'vitest'
import { ArchFileSchema } from '@/types/arch'

describe('ArchFileSchema', () => {
  it('parses a well-formed response', () => {
    const parsed = ArchFileSchema.parse({
      name: 'gsm8k.yaml',
      text: 'flow: |\n  a --> b',
      architecture: { nodes: [], edges: [], flow: 'a --> b' },
      warnings: [],
    })
    expect(parsed.name).toBe('gsm8k.yaml')
  })

  it('rejects a response missing warnings', () => {
    expect(() =>
      ArchFileSchema.parse({ name: 'x.yaml', text: '', architecture: {} }),
    ).toThrow()
  })
})
