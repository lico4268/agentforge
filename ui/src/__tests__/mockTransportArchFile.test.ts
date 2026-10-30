import { describe, expect, it, vi } from 'vitest'
import { MockTransport } from '@/transport/MockTransport'
import type { ServerMessage } from '@/transport/protocol'

// Review finding 3: if MockTransport silently ignores an archFile-only run, then without a backend
// connection (VITE_WS_URL unset, the npm run dev default) the Run button looks dead with no
// response — it's the first button pressed when first checking this feature, and there'd be no signal
// at all. An explicit error message must be emitted.
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
