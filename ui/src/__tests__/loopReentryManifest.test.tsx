import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { GenericNode } from '@/canvas/nodes/GenericNode'
import { NodeManifestListSchema } from '@/types'

const loopReentry = BUILTIN_MANIFESTS.find((m) => m.type === 'loop.reentry')!

describe('loop.reentry 매니페스트', () => {
  it('In 입력 1개와 Out 출력 1개를 선언한다', () => {
    expect(loopReentry).toBeDefined()
    expect(loopReentry.inputs.map((p) => [p.id, p.label])).toEqual([['in', 'In']])
    expect(loopReentry.outputs.map((p) => [p.id, p.label])).toEqual([['out', 'Out']])
    expect(loopReentry.config).toEqual([])
  })

  it("runtime 'passthrough'가 NodeManifestSchema를 통과한다", () => {
    expect(() => NodeManifestListSchema.parse(BUILTIN_MANIFESTS)).not.toThrow()
    expect(loopReentry.runtime).toBe('passthrough')
    expect(loopReentry.category).toBe('policy')
  })
})

describe('loop.reentry 렌더링', () => {
  it('커스텀 렌더러 없이 GenericNode가 In/Out 포트를 그린다', () => {
    const registry = new NodeRegistry(BUILTIN_MANIFESTS)
    expect(registry.customComponent('loop.reentry')).toBeUndefined()

    const props = {
      id: 'reentry-1',
      type: 'loop.reentry',
      data: { manifestType: 'loop.reentry', config: {} },
      selected: false,
      dragging: false,
      zIndex: 0,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
    } as unknown as NodeProps

    render(
      <ReactFlowProvider>
        <RegistryProvider value={registry}>
          <GenericNode {...props} />
        </RegistryProvider>
      </ReactFlowProvider>,
    )

    expect(screen.getByText('Loop Start')).toBeInTheDocument()
    expect(screen.getByText('In')).toBeInTheDocument()
    expect(screen.getByText('Out')).toBeInTheDocument()
  })
})
