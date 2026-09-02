import type { Architecture, ExecutionEvent } from '@/types'
import type { Transport } from './Transport'
import type { ClientMessage, ServerMessage } from './protocol'

/**
 * Backend-free transport for developing the canvas (ui-architecture.md §7).
 * On `run`, it walks the graph in dependency order and emits realistic
 * start/end events with delays, so the live-highlight pipeline can be built
 * and demoed before FastAPI exists.
 */
export class MockTransport implements Transport {
  private handlers = new Set<(msg: ServerMessage) => void>()
  private timers: ReturnType<typeof setTimeout>[] = []

  async connect() {}

  disconnect() {
    this.clearTimers()
    this.handlers.clear()
  }

  subscribe(handler: (msg: ServerMessage) => void) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  send(msg: ClientMessage) {
    if (msg.kind === 'run') {
      if (msg.architecture) {
        this.simulate(msg.architecture)
      } else if (msg.archFile) {
        // archFile(텍스트 우선 대시보드)로 오는 run은 MockTransport가 시뮬레이션할
        // 캔버스 그래프가 없다 — 조용히 무시하면 Run 버튼이 아무 반응 없이 죽어
        // 보인다(리뷰 finding 3, 이게 사람이 이 기능을 눈으로 확인할 때 제일 먼저
        // 누르는 버튼이다). 실제 백엔드가 필요하다고 명시적으로 알려준다.
        this.handlers.forEach((h) =>
          h({
            kind: 'error',
            message:
              "Mock transport can't run arch.yaml files — set VITE_WS_URL to a running backend (see ui/.env).",
          }),
        )
      }
    }
    if (msg.kind === 'stop') this.clearTimers()
  }

  private emit(event: ExecutionEvent) {
    const msg: ServerMessage = { kind: 'event', event }
    this.handlers.forEach((h) => h(msg))
  }

  private clearTimers() {
    this.timers.forEach(clearTimeout)
    this.timers = []
  }

  private simulate(arch: Architecture) {
    this.clearTimers()
    const runId = `mock-${Date.now()}`
    const order = topoOrder(arch)
    const stepMs = 700
    let cursor = 0

    // 실행 시작 알림
    this.schedule(0, () =>
      this.handlers.forEach((h) => h({ kind: 'run_started', runId })),
    )

    for (const nodeId of order) {
      const startAt = cursor
      const endAt = cursor + stepMs

      const isReview = arch.nodes.find((n) => n.id === nodeId)?.type.startsWith(
        'review.',
      )
      // Demo a conditional review: skip the *next* node sometimes.
      const policyDecision = isReview
        ? {
            activated: Math.random() > 0.5,
            branch: Math.random() > 0.5 ? 'accept' : 'refine',
            reason: 'mock intent alignment review',
          }
        : undefined

      this.schedule(startAt, () =>
        this.emit(makeEvent('node_start', runId, nodeId)),
      )
      this.schedule(endAt, () =>
        this.emit(
          makeEvent('node_end', runId, nodeId, {
            durationMs: stepMs,
            tokenUsage: { prompt: 120 + Math.floor(Math.random() * 400), completion: 80 + Math.floor(Math.random() * 300) },
            policyDecision,
            output: { preview: `output of ${nodeId}` },
          }),
        ),
      )
      cursor = endAt + 120
    }

    // 마지막 노드 완료 후 run_complete 발송
    const totalMs = cursor
    this.schedule(totalMs, () =>
      this.handlers.forEach((h) =>
        h({
          kind: 'run_complete',
          runId,
          result: { answer: `Mock run finished (${order.length} nodes)`, reviewDelta: null },
        }),
      ),
    )
  }

  private schedule(delay: number, fn: () => void) {
    this.timers.push(setTimeout(fn, delay))
  }
}

function makeEvent(
  eventType: ExecutionEvent['eventType'],
  runId: string,
  nodeId: string,
  extra: Partial<ExecutionEvent> = {},
): ExecutionEvent {
  return {
    eventType,
    runId,
    nodeId,
    timestamp: new Date().toISOString(),
    ...extra,
  }
}

/** Kahn topological sort; falls back to insertion order on cycles. */
function topoOrder(arch: Architecture): string[] {
  const indeg = new Map<string, number>()
  const adj = new Map<string, string[]>()
  arch.nodes.forEach((n) => {
    indeg.set(n.id, 0)
    adj.set(n.id, [])
  })
  arch.edges.forEach((e) => {
    if (!adj.has(e.source) || !indeg.has(e.target)) return
    adj.get(e.source)!.push(e.target)
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
  })
  const queue = arch.nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
  const out: string[] = []
  while (queue.length) {
    const id = queue.shift()!
    out.push(id)
    for (const next of adj.get(id) ?? []) {
      indeg.set(next, (indeg.get(next) ?? 1) - 1)
      if (indeg.get(next) === 0) queue.push(next)
    }
  }
  return out.length === arch.nodes.length ? out : arch.nodes.map((n) => n.id)
}
