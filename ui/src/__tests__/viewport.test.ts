import { describe, expect, it } from 'vitest'
import { viewportTransitionDuration } from '@/canvas/viewport'

describe('viewportTransitionDuration', () => {
  it('disables viewport animation when reduced motion is requested', () => {
    expect(viewportTransitionDuration(true)).toBe(0)
    expect(viewportTransitionDuration(false)).toBe(200)
  })
})
