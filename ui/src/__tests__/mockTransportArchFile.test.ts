import { describe, expect, it, vi } from 'vitest'
import { MockTransport } from '@/transport/MockTransport'
import type { ServerMessage } from '@/transport/protocol'

// 리뷰 finding 3: archFile-only run을 MockTransport가 조용히 무시하면, 백엔드
// 연결 없이 (VITE_WS_URL 미설정, npm run dev 기본값) Run 버튼이 아무 반응 없이
// 죽어 보인다 — 이 기능을 눈으로 처음 확인할 때 제일 먼저 누르는 버튼인데 신호가
// 전혀 없다. 명시적인 error 메시지를 emit해야 한다.
describe('MockTransport — archFile-only run', () => {
  it('emits an explanatory error instead of silently doing nothing', () => {
    const transport = new MockTransport()
    const messages: ServerMessage[] = []
    transport.subscribe((msg) => messages.push(msg))

    transport.send({ kind: 'run', archFile: 'gsm8k.yaml', input: null })

    expect(messages).toHaveLength(1)
    expect(messages[0].kind).toBe('error')
    expect((messages[0] as { message: string }).message).toMatch(/VITE_WS_URL/)
  })

  it('still simulates a normal canvas run when architecture is present', () => {
    vi.useFakeTimers()
    const transport = new MockTransport()
    const messages: ServerMessage[] = []
    transport.subscribe((msg) => messages.push(msg))

    transport.send({
      kind: 'run',
      architecture: {
        version: '0.1',
        metadata: { name: 'x', createdAt: '2026-01-01' },
        nodes: [],
        edges: [],
      },
      input: null,
    })
    vi.runAllTimers()
    vi.useRealTimers()

    expect(messages.some((m) => m.kind === 'run_started')).toBe(true)
  })
})
