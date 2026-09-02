import type { ExecutionEvent } from '@/types'
import type { PendingInterrupt } from '@/execution/useExecutionStore'
import type { ProgressEntry } from './NodeProgress'

/**
 * 실행 이벤트 스트림(store의 `events`, 등장 순서 그대로)을 `NodeProgress`가 그릴
 * 방문 목록으로 접는다. 같은 nodeId가 여러 번 `node_start`하면 매번 새 항목이
 * 열린다 — 그래야 NodeProgress의 #1/#2 재방문 번호가 의미를 갖는다.
 *
 * 루프의 합성 가드 노드(`__guard_N`)도 다른 노드와 동일하게 취급한다 — flow
 * 문자열/다이어그램에는 없지만 이벤트는 실제로 온다(설계 결정, task-6 브리프
 * 참고). 다이어그램 색칠에서만 걸러낸다(`deriveFlowStatuses`).
 */
export function buildProgressEntries(
  events: ExecutionEvent[],
  pendingInterrupt: PendingInterrupt | null,
): ProgressEntry[] {
  const entries: ProgressEntry[] = []

  for (const event of events) {
    if (event.eventType === 'node_start') {
      entries.push({ nodeId: event.nodeId, status: 'running', durationMs: null, output: null })
      continue
    }
    const idx = findLastRunning(entries, event.nodeId)
    if (idx === -1) continue

    if (event.eventType === 'node_end') {
      const skipped = event.policyDecision?.activated === false
      entries[idx] = {
        ...entries[idx],
        status: skipped ? 'skipped' : 'done',
        durationMs: event.durationMs ?? null,
        output: event.output ?? null,
      }
    } else if (event.eventType === 'error') {
      entries[idx] = {
        ...entries[idx],
        status: 'failed',
        output: event.error ?? null,
      }
    }
  }

  if (pendingInterrupt) {
    const idx = findLastRunning(entries, pendingInterrupt.nodeId)
    const paused: ProgressEntry = {
      nodeId: pendingInterrupt.nodeId,
      status: 'paused',
      durationMs: null,
      output: pendingInterrupt.payload,
    }
    if (idx === -1) entries.push(paused)
    else entries[idx] = paused
  }

  return entries
}

function findLastRunning(entries: ProgressEntry[], nodeId: string): number {
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].nodeId === nodeId && entries[i].status === 'running') return i
  }
  return -1
}

/**
 * FlowDiagram에 넘길 상태 맵 — entries 중 mermaid `flow` 문자열에 실제로 등장하는
 * nodeId만 남긴다. `__guard_N`처럼 flow에 없는 id를 그대로 넘기면 mermaid가 그
 * id로 된 빈 노드를 다이어그램에 몰래 추가해버린다(class 지시어가 미선언 노드를
 * 암묵적으로 생성) — 그림이 flow 문자열과 달라지는 것을 막기 위한 필터다.
 *
 * ponytail: 진짜 파서 대신 단어 토큰 매칭이라 엣지 라벨 텍스트의 단어와 우연히
 * 같은 실제 nodeId가 있으면 과포함될 수 있다(해될 것 없음 — 실제 노드이므로 원래
 * 그려야 한다) — 반대로 실제 노드 id가 라벨에도 없이 완전히 걸러지는 방향의
 * 오탐은 나지 않는다. flow에 진짜 그래프 구조를 부여하려면 서버의 `nodes` 목록과
 * 대조해야 하는데, 그건 flow 문자열이 아닌 별도 데이터라 여기 책임 밖이다.
 */
export function deriveFlowStatuses(
  entries: ProgressEntry[],
  flow: string,
): Record<string, 'running' | 'done' | 'failed'> {
  const flowTokens = new Set(flow.match(/[A-Za-z0-9_.:-]+/g) ?? [])
  const out: Record<string, 'running' | 'done' | 'failed'> = {}
  for (const e of entries) {
    if ((e.status === 'running' || e.status === 'done' || e.status === 'failed') && flowTokens.has(e.nodeId)) {
      out[e.nodeId] = e.status
    }
  }
  return out
}
