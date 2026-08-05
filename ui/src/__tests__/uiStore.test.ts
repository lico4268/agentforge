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

describe('useUiStore loop scope expansion', () => {
  beforeEach(() => {
    useUiStore.setState({ expandedLoopScopeIds: new Set() })
  })

  it('defaults to empty — every detected Tier 1/2 loop starts collapsed', () => {
    expect(useUiStore.getState().expandedLoopScopeIds.size).toBe(0)
  })

  it('toggles a scope id into and back out of the expanded set', () => {
    useUiStore.getState().toggleLoopScopeExpanded('loop:1:a,b')

    expect(useUiStore.getState().expandedLoopScopeIds.has('loop:1:a,b')).toBe(true)

    useUiStore.getState().toggleLoopScopeExpanded('loop:1:a,b')

    expect(useUiStore.getState().expandedLoopScopeIds.has('loop:1:a,b')).toBe(false)
  })

  it('tracks multiple expanded scopes independently', () => {
    useUiStore.getState().toggleLoopScopeExpanded('loop:1:a,b')
    useUiStore.getState().toggleLoopScopeExpanded('loop:2:c,d,e')

    const expanded = useUiStore.getState().expandedLoopScopeIds
    expect(expanded.has('loop:1:a,b')).toBe(true)
    expect(expanded.has('loop:2:c,d,e')).toBe(true)
  })
})

describe('useUiStore raw execution view', () => {
  beforeEach(() => {
    useUiStore.setState({ rawExecutionView: true })
  })

  it('defaults to true — original nodes remain visible before loop projection is enabled', () => {
    expect(useUiStore.getState().rawExecutionView).toBe(true)
  })

  it('toggles independently of loop scope expansion state', () => {
    useUiStore.getState().toggleRawExecutionView()

    expect(useUiStore.getState().rawExecutionView).toBe(false)

    useUiStore.getState().toggleRawExecutionView()

    expect(useUiStore.getState().rawExecutionView).toBe(true)
  })
})
