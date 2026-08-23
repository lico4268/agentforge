import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { Inspector } from '@/panels/Inspector'
import type { Port } from '@/types'

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

// custom.node(Phase B④): 완전히 빈 노드 — 이름과 입출력 포트를 인스턴스별로
// Inspector에서 직접 편집한다. 포트는 전부 텍스트 타입, +/- 로만 늘리고 줄인다.
describe('Inspector — custom.node 이름/포트 편집', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
    )
    useGraphStore.setState({ nodes: [], edges: [], selectedNodeId: null })
    useGraphStore.getState().addNode('custom.node', { x: 0, y: 0 })
    const nodeId = useGraphStore.getState().nodes[0].id
    useGraphStore.getState().select(nodeId)
  })

  it('이름 필드를 편집하면 config.label에 저장된다', () => {
    renderInspector()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Extract Keywords' } })

    expect(useGraphStore.getState().nodes[0].data.config.label).toBe('Extract Keywords')
  })

  it('Add Output을 누르면 텍스트 타입 출력 포트가 하나 추가된다', () => {
    renderInspector()

    fireEvent.click(screen.getByText('Add Output'))

    const outputs = useGraphStore.getState().nodes[0].data.config.outputs as Port[]
    expect(outputs).toHaveLength(1)
    expect(outputs[0]).toMatchObject({ label: 'Port 1', dataType: 'text' })
  })

  it('Add Input을 누르면 입력 포트가 하나 추가된다', () => {
    renderInspector()

    fireEvent.click(screen.getByText('Add Input'))

    const inputs = useGraphStore.getState().nodes[0].data.config.inputs as Port[]
    expect(inputs).toHaveLength(1)
  })

  it('포트 라벨을 편집해도 id는 최초 생성된 값 그대로 유지된다', () => {
    renderInspector()
    fireEvent.click(screen.getByText('Add Output'))
    const idBefore = (useGraphStore.getState().nodes[0].data.config.outputs as Port[])[0].id

    fireEvent.change(screen.getByDisplayValue('Port 1'), { target: { value: 'Summary' } })

    const output = (useGraphStore.getState().nodes[0].data.config.outputs as Port[])[0]
    expect(output.label).toBe('Summary')
    expect(output.id).toBe(idBefore)
  })

  it('제거 버튼을 누르면 그 포트만 삭제되고 나머지는 남는다', () => {
    renderInspector()
    fireEvent.click(screen.getByText('Add Output'))
    fireEvent.click(screen.getByText('Add Output'))
    fireEvent.change(screen.getAllByDisplayValue(/Port \d/)[0], { target: { value: 'Keep Me' } })

    fireEvent.click(screen.getAllByTitle('Remove port')[1])

    const outputs = useGraphStore.getState().nodes[0].data.config.outputs as Port[]
    expect(outputs).toHaveLength(1)
    expect(outputs[0].label).toBe('Keep Me')
  })
})
