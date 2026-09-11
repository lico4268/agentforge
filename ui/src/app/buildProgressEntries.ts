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
 * FlowDiagram에 넘길 상태 맵 — `nodeIds`(백엔드가 준 `architecture.nodes[].id`,
 * 권위 있는 목록)에 실제로 있는 nodeId만 남긴다.
 *
 * 예전 구현은 `flow` mermaid 문자열을 정규식으로 토큰화해서 멤버십을 판단했는데,
 * 노드 이름에 비ASCII 문자(한글 등, 설계 스펙 §3.3의 예시 자체가 `초안`/`검토`)가
 * 오면 토큰 정규식이 그 글자들을 아예 못 잡아 다이어그램 색칠이 조용히 실패했다
 * (리뷰 finding 1). `architecture.nodes`는 서버가 이미 파싱해서 준 권위 있는
 * id 목록이라 재파싱이 필요 없다 — 이 목록을 직접 쓰면 이 문제가 클래스째 사라진다.
 *
 * `__guard_N`(루프 합성 가드)은 `architecture.nodes`에는 있지만 flow 문자열/
 * 다이어그램에는 없으므로 (mermaid의 `class` 지시어가 미선언 노드를 암묵
 * 생성해 그림에 낯선 상자를 만들지 않도록) 여기서 걸러낸다.
 */
export function deriveFlowStatuses(
  entries: ProgressEntry[],
  nodeIds: Iterable<string>,
): Record<string, 'running' | 'done' | 'failed'> {
  const valid = new Set(Array.from(nodeIds).filter((id) => !id.startsWith('__guard_')))
  const out: Record<string, 'running' | 'done' | 'failed'> = {}
  for (const e of entries) {
    if ((e.status === 'running' || e.status === 'done' || e.status === 'failed') && valid.has(e.nodeId)) {
      out[e.nodeId] = e.status
    }
  }
  return out
}
