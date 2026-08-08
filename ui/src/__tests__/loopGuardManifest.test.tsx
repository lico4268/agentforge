import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { GenericNode } from '@/canvas/nodes/GenericNode'
import {
  LOOP_POLICY_EXHAUSTION_ACTIONS,
  LOOP_POLICY_KINDS,
  NodeManifestListSchema,
} from '@/types'

const loopGuard = BUILTIN_MANIFESTS.find((m) => m.type === 'loop.guard')!

describe('loop.guard 매니페스트', () => {
  it('Feedback 입력 1개와 Loop back / Exit 출력 2개를 선언한다', () => {
    expect(loopGuard).toBeDefined()
    expect(loopGuard.inputs.map((p) => [p.id, p.label])).toEqual([['in', 'Feedback']])
    expect(loopGuard.outputs.map((p) => [p.id, p.label])).toEqual([
      ['loopBack', 'Loop back'],
      ['exit', 'Exit'],
    ])
  })

  it("runtime 'loop_guard'가 NodeManifestSchema를 통과한다", () => {
    // RUNTIMES에 'loop_guard'가 없으면 loadManifests()가 백엔드 목록 전체를 조용히
    // 버리고 번들 폴백으로 떨어진다 — 그 회귀를 여기서 막는다.
    expect(() => NodeManifestListSchema.parse(BUILTIN_MANIFESTS)).not.toThrow()
    expect(loopGuard.runtime).toBe('loop_guard')
    expect(loopGuard.category).toBe('policy')
  })

  it('5축 guard config 필드를 순서대로 노출한다', () => {
    expect(loopGuard.config.map((f) => f.key)).toEqual([
      'kind',
      'maxIterations',
      'maxTokens',
      'maxCostUsd',
      'maxDurationSec',
      'stuckWindow',
      'stuckThreshold',
      'onExhaustion',
    ])
  })

  it('kind/onExhaustion 옵션 값이 공유 상수에서 나온다', () => {
    const values = (key: string) =>
      loopGuard.config.find((f) => f.key === key)?.options?.map((o) => o.value)
    expect(values('kind')).toEqual([...LOOP_POLICY_KINDS])
    expect(values('onExhaustion')).toEqual([...LOOP_POLICY_EXHAUSTION_ACTIONS])
  })
})

describe('loop.guard 렌더링', () => {
  it('커스텀 렌더러 없이 GenericNode가 두 출력 포트를 그린다', () => {
    const registry = new NodeRegistry(BUILTIN_MANIFESTS)
    expect(registry.customComponent('loop.guard')).toBeUndefined()

    const props = {
      id: 'loop-1',
      type: 'loop.guard',
      data: { manifestType: 'loop.guard', config: {} },
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

    expect(screen.getByText('Loop')).toBeInTheDocument()
    expect(screen.getByText('Feedback')).toBeInTheDocument()
    expect(screen.getByText('Loop back')).toBeInTheDocument()
    expect(screen.getByText('Exit')).toBeInTheDocument()
  })
})
