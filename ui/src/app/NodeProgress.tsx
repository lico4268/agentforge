import { useState } from 'react'
import { Markdown } from '@/panels/Markdown'

export type ProgressEntry = {
  nodeId: string
  status: 'running' | 'done' | 'failed' | 'paused' | 'skipped'
  durationMs: number | null
  output: unknown
}

const MARK = { running: '▸', done: '✓', failed: '✗', paused: '⏸', skipped: '·' } as const

/** 같은 노드가 여러 번 방문되면 #1, #2로 번호를 붙인다. 한 번뿐이면 번호 없음
 * — 루프가 없는 그래프에 잡음을 더하지 않는다 (설계 §5.1 회차 구분). */
function label(entries: ProgressEntry[], index: number): string {
  const { nodeId } = entries[index]
  const total = entries.filter((e) => e.nodeId === nodeId).length
  if (total < 2) return nodeId
  const nth = entries.slice(0, index + 1).filter((e) => e.nodeId === nodeId).length
  return `${nodeId} #${nth}`
}

/**
 * 실행 이벤트를 노드별 방문 목록으로 나열한다. `entries`는 diagram과 무관하게
 * 이벤트가 있었던 모든 nodeId를 그대로 보여준다 — 루프의 합성 가드 노드
 * (`__guard_N`, flow 문자열/다이어그램에는 없음)도 여기서는 평범한 항목 하나로
 * 나온다. 다이어그램 색칠(FlowDiagram)에서만 그런 id를 걸러낸다.
 */
export function NodeProgress({
  entries,
  onResume,
}: {
  entries: ProgressEntry[]
  onResume: (decision: string) => void
}) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <ul className="node-progress">
      {entries.map((entry, i) => (
        <li key={`${entry.nodeId}-${i}`}>
          <button type="button" onClick={() => setOpen(open === i ? null : i)}>
            <span>{MARK[entry.status]}</span>
            <span>{label(entries, i)}</span>
            {entry.durationMs !== null && <span>{(entry.durationMs / 1000).toFixed(1)}s</span>}
          </button>
          {entry.status === 'paused' && (
            <span className="checkpoint-actions">
              {['approve', 'revise', 'reject'].map((d) => (
                <button key={d} type="button" onClick={() => onResume(d)}>
                  {d}
                </button>
              ))}
            </span>
          )}
          {open === i && entry.output != null && (
            <Markdown>
              {typeof entry.output === 'string' ? entry.output : JSON.stringify(entry.output, null, 2)}
            </Markdown>
          )}
        </li>
      ))}
    </ul>
  )
}
