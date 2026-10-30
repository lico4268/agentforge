import mermaid from 'mermaid'
import { useEffect, useRef } from 'react'

mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })

/** Renders the arch.yaml flow string as-is — no conversion code (design §3.2).
 * Execution status is coloured by appending a single classDef line. `statuses` is assumed
 * to have already been filtered (in the Dashboard's `deriveFlowStatuses`) to nodeIds that
 * actually appear in the flow. */
export function FlowDiagram({
  flow,
  statuses,
}: {
  flow: string
  statuses: Record<string, 'running' | 'done' | 'failed'>
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const classes = Object.entries(statuses)
      .map(([nodeId, status]) => `class ${nodeId} ${status}`)
      .join('\n')
    // If the arch.yaml author already wrote a flowchart/graph directive on the first line of the
    // flow: block (so it renders when pasted into GitHub/Obsidian as-is, design §3.2), we don't
    // prepend another one — mermaid doesn't allow two directive lines.
    const hasDirective = /^\s*(flowchart|graph)\b/.test(flow)
    const source = [
      ...(hasDirective ? [] : ['flowchart LR']),
      flow,
      'classDef running fill:#2563eb,color:#fff',
      'classDef done fill:#16a34a,color:#fff',
      'classDef failed fill:#dc2626,color:#fff',
      classes,
    ].join('\n')
    let cancelled = false
    mermaid
      .render(`flow-${Date.now()}`, source)
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      })
      .catch((err: unknown) => {
        if (!cancelled && ref.current) ref.current.textContent = String(err)
      })
    return () => {
      cancelled = true
    }
  }, [flow, statuses])
  return <div className="flow-diagram" ref={ref} />
}
