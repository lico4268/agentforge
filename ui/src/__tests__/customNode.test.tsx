import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { GenericNode } from '@/canvas/nodes/GenericNode'
import { AgentNode } from '@/canvas/nodes/AgentNode'
import { NodeManifestListSchema } from '@/types'

const customNode = BUILTIN_MANIFESTS.find((m) => m.type === 'custom.node')!

describe('custom.node 매니페스트', () => {
  it('입출력 포트가 전부 비어있다 — 인스턴스 config가 채운다', () => {
    expect(customNode).toBeDefined()
    expect(customNode.inputs).toEqual([])
    expect(customNode.outputs).toEqual([])
  })

  it("runtime 'llm_step'가 NodeManifestSchema를 통과한다", () => {
    expect(() => NodeManifestListSchema.parse(BUILTIN_MANIFESTS)).not.toThrow()
    expect(customNode.runtime).toBe('llm_step')
  })
})

function renderCustomNode(config: Record<string, unknown>) {
  const registry = new NodeRegistry(BUILTIN_MANIFESTS)
  const props = {
    id: 'custom-1',
    type: 'custom.node',
    data: { manifestType: 'custom.node', config },
    selected: false,
    dragging: false,
    zIndex: 0,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps

  return render(
    <ReactFlowProvider>
      <RegistryProvider value={registry}>
        <GenericNode {...props} />
      </RegistryProvider>
    </ReactFlowProvider>,
  )
}

describe('custom.node 렌더링 — 인스턴스 config가 포트/라벨을 대체한다', () => {
  it('config.label이 있으면 매니페스트 라벨("Custom") 대신 그걸 보여준다', () => {
    renderCustomNode({ label: 'Extract Keywords' })
    expect(screen.getByText('Extract Keywords')).toBeInTheDocument()
    expect(screen.queryByText('Custom')).not.toBeInTheDocument()
  })

  it('config.label이 없으면 매니페스트 라벨("Custom")을 그대로 보여준다', () => {
    renderCustomNode({})
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  it('config.inputs/config.outputs 포트를 렌더링한다 — 매니페스트는 비어있음에도', () => {
    renderCustomNode({
      inputs: [{ id: 'text', label: 'Text', dataType: 'text' }],
      outputs: [{ id: 'summary', label: 'Summary', dataType: 'text' }],
    })
    expect(screen.getByText('Text')).toBeInTheDocument()
    expect(screen.getByText('Summary')).toBeInTheDocument()
  })
})

describe('custom.node 렌더링 (agent 모드) — 인스턴스 config가 라벨을 대체한다', () => {
  function renderAgentCustomNode(config: Record<string, unknown>) {
    const registry = new NodeRegistry(BUILTIN_MANIFESTS)
    const props = {
      id: 'custom-1',
      type: 'custom.node',
      data: { manifestType: 'custom.node', config },
      selected: false,
      dragging: false,
      zIndex: 0,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
    } as unknown as NodeProps

    return render(
      <ReactFlowProvider>
        <RegistryProvider value={registry}>
          <AgentNode {...props} />
        </RegistryProvider>
      </ReactFlowProvider>,
    )
  }

  it('config.label이 있으면 원형 노드에도 그걸 보여준다', () => {
    renderAgentCustomNode({ label: 'Extract Keywords' })
    expect(screen.getByText('Extract Keywords')).toBeInTheDocument()
  })

  it('config.label이 없으면 매니페스트 라벨("Custom")을 보여준다', () => {
    renderAgentCustomNode({})
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })
})
