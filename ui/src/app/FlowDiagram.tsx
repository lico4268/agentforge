import mermaid from 'mermaid'
import { useEffect, useRef } from 'react'

mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })

/** arch.yaml의 flow 문자열을 그대로 렌더한다 — 변환 코드 없음 (설계 §3.2).
 * 실행 상태는 classDef 한 줄을 덧붙여 색칠한다. `statuses`는 이미
 * (Dashboard의 `deriveFlowStatuses`에서) flow에 실제로 등장하는 nodeId로
 * 걸러져서 들어온다고 가정한다. */
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
    // arch.yaml 저자가 flow: 블록 첫 줄에 이미 flowchart/graph 지시문을 적어뒀으면
    // (GitHub/Obsidian에 그대로 붙여넣어 렌더되게 하려고, 설계 §3.2) 우리가 또
    // 하나 앞에 붙이지 않는다 — mermaid는 지시문 두 줄을 허용하지 않는다.
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
