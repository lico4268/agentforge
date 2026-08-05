import { describe, expect, it } from 'vitest'
import { edgePresentation } from '@/canvas/edges/edgePresentation'

describe('edgePresentation', () => {
  it('marks review and checkpoint branch handles as conditional', () => {
    expect(edgePresentation('accept')).toEqual({ conditional: true, color: '#4edea3' })
    expect(edgePresentation('refine').conditional).toBe(true)
    expect(edgePresentation('clarify')).toEqual({ conditional: true, color: '#ffd180' })
    expect(edgePresentation('reject')).toEqual({ conditional: true, color: '#ff8a80' })
  })

  it('keeps ordinary data handles unlabelled by default', () => {
    expect(edgePresentation('answer')).toEqual({ conditional: false, color: '#6f8175' })
    expect(edgePresentation(undefined)).toEqual({ conditional: false, color: '#6f8175' })
  })
})
