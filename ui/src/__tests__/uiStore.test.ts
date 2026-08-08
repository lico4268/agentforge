import { beforeEach, describe, expect, it } from 'vitest'
import { useUiStore } from '@/stores/useUiStore'

describe('useUiStore canvas node mode', () => {
  beforeEach(() => {
    useUiStore.setState({ canvasNodeMode: 'classic' })
  })

  it('switches render mode without changing graph state', () => {
    useUiStore.getState().setCanvasNodeMode('agent')

    expect(useUiStore.getState().canvasNodeMode).toBe('agent')
  })

})

describe('useUiStore connection port visibility', () => {
  beforeEach(() => {
    useUiStore.setState({ showConnectionPorts: false })
  })

  it('defaults to hidden — ports only appear while actively editing connections', () => {
    expect(useUiStore.getState().showConnectionPorts).toBe(false)
  })

  it('toggles independently of canvas node mode', () => {
    useUiStore.getState().toggleConnectionPorts()

    expect(useUiStore.getState().showConnectionPorts).toBe(true)

    useUiStore.getState().toggleConnectionPorts()

    expect(useUiStore.getState().showConnectionPorts).toBe(false)
  })
})
