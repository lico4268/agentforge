import { describe, expect, it } from 'vitest'
import { ArchitectureSchema } from '@/types'
import { STARTER_ARCHITECTURE } from '@/app/starterArchitecture'

const guard = () => STARTER_ARCHITECTURE.nodes.find((n) => n.type === 'loop.guard')

describe('STARTER_ARCHITECTURE', () => {
  it('ArchitectureSchema를 통과한다', () => {
    expect(() => ArchitectureSchema.parse(STARTER_ARCHITECTURE)).not.toThrow()
  })

  it('refine 피드백이 loop.guard 노드로 들어간다', () => {
    const refine = STARTER_ARCHITECTURE.edges.find((e) => e.sourceHandle === 'refine')
    expect(guard()).toBeDefined()
    expect(refine?.target).toBe(guard()!.id)
    expect(refine?.targetHandle).toBe('in')
  })

  it('loop.guard의 loopBack/exit 포트가 모두 배선돼 있다', () => {
    // 백엔드 compile_graph는 둘 중 하나라도 비면 ValueError를 던진다.
    const handles = STARTER_ARCHITECTURE.edges
      .filter((e) => e.source === guard()!.id)
      .map((e) => e.sourceHandle)
      .sort()
    expect(handles).toEqual(['exit', 'loopBack'])
  })

  it('reasoning으로 되돌아오는 유일한 피드백 경로가 loop.guard를 거친다', () => {
    // 가드를 우회하는 되돌림 엣지가 하나라도 있으면 ungated cycle 컴파일 에러가 난다.
    const feedbackIntoReasoning = STARTER_ARCHITECTURE.edges
      .filter((e) => e.target === 'reasoning' && !['input', 'planning'].includes(e.source))
      .map((e) => e.source)
    expect(feedbackIntoReasoning).toEqual([guard()!.id])
  })

  it('가드에 유한한 maxIterations와 exit 소진 정책이 설정돼 있다', () => {
    expect(guard()!.config.maxIterations).toBe(3)
    expect(guard()!.config.onExhaustion).toBe('exit')
  })
})
