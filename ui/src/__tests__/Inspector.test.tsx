import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { Inspector } from '@/panels/Inspector'

function renderInspector() {
  const registry = new NodeRegistry(BUILTIN_MANIFESTS)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RegistryProvider value={registry}>
        <Inspector />
      </RegistryProvider>
    </QueryClientProvider>,
  )
}

// loop.guard의 6개 가드 축(maxIterations 등)은 manifest에 default가 없다 — unset일 때
// Number(undefined ?? 0)으로 0을 보여주던 버그와, 비워도 0이 config에 박히던 버그를
// 둘 다 재현/방지한다.
describe('Inspector — loop.guard 숫자 필드', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    )
    useGraphStore.setState({ nodes: [], edges: [], selectedNodeId: null })
    useGraphStore.getState().addNode('loop.guard', { x: 0, y: 0 })
    const nodeId = useGraphStore.getState().nodes[0].id
    useGraphStore.getState().select(nodeId)
  })

  it('default가 없는 축은 unset일 때 빈 입력으로 렌더된다 (0이 아니다)', () => {
    renderInspector()

    const input = screen.getByLabelText('Max iterations') as HTMLInputElement
    expect(input).toHaveValue(null)
    expect(input.value).toBe('')
  })

  it('값을 입력했다가 지우면 config에서 키 자체가 사라진다 (0이 남지 않는다)', () => {
    renderInspector()

    const input = screen.getByLabelText('Max iterations') as HTMLInputElement

    fireEvent.change(input, { target: { value: '5' } })
    expect(useGraphStore.getState().nodes[0].data.config.maxIterations).toBe(5)

    fireEvent.change(screen.getByLabelText('Max iterations'), { target: { value: '' } })

    const config = useGraphStore.getState().nodes[0].data.config
    expect('maxIterations' in config).toBe(false)
    expect(screen.getByLabelText('Max iterations')).toHaveValue(null)
  })

  it('실제 0은 유효한 값으로 남는다 (unset과 구분된다)', () => {
    renderInspector()

    const input = screen.getByLabelText('Max iterations') as HTMLInputElement
    fireEvent.change(input, { target: { value: '0' } })

    const config = useGraphStore.getState().nodes[0].data.config
    expect(config.maxIterations).toBe(0)
    expect(screen.getByLabelText('Max iterations')).toHaveValue(0)
  })
})
