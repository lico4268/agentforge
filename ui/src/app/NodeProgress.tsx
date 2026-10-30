import { useState } from 'react'
import { Markdown } from '@/panels/Markdown'

export type ProgressEntry = {
  nodeId: string
  status: 'running' | 'done' | 'failed' | 'paused' | 'skipped'
  durationMs: number | null
  output: unknown
}

const MARK = { running: '▸', done: '✓', failed: '✗', paused: '⏸', skipped: '·' } as const

/** If the same node is visited multiple times, number the visits #1, #2. A single visit gets no number
 * — no added noise for graphs without loops (design §5.1 per-iteration distinction). */
function label(entries: ProgressEntry[], index: number): string {
  const { nodeId } = entries[index]
  const total = entries.filter((e) => e.nodeId === nodeId).length
  if (total < 2) return nodeId
  const nth = entries.slice(0, index + 1).filter((e) => e.nodeId === nodeId).length
  return `${nodeId} #${nth}`
}

/**
 * Lists execution events as a per-node visit list. `entries` shows every nodeId that had
 * events, independent of the diagram — a loop's synthetic guard node
 * (`__guard_N`, not in the flow string/diagram) also appears here as an ordinary entry.
 * Only diagram colouring (FlowDiagram) filters such ids out.
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
