import type { MouseEvent } from 'react'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import type { LoopAnchor as LoopAnchorData } from '@/canvas/loops/loopAnchors'

type Props = {
  anchor: LoopAnchorData
  index: number
  selected: boolean
}

const LOOP_ACCENT = '#a78bfa'

export function LoopAnchor({ anchor, index, selected }: Props) {
  const select = useGraphStore((state) => state.select)
  const hoveredLoopCandidateId = useUiStore((state) => state.hoveredLoopCandidateId)
  const setHoveredLoopCandidateId = useUiStore((state) => state.setHoveredLoopCandidateId)
  const active = selected || hoveredLoopCandidateId === anchor.candidateId
  const isSource = anchor.role === 'feedbackSource'

  const selectLoop = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    select(anchor.candidateId)
  }

  return (
    <button
      type="button"
      className={`nodrag nopan absolute z-20 flex h-9 min-w-9 items-center justify-center rounded-full p-1 transition-[background-color,border-color,color,box-shadow] duration-200 motion-reduce:transition-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ddd6fe] ${
        isSource ? '-right-5' : '-left-5'
      }`}
      style={{
        top: isSource ? 8 + index * 24 : undefined,
        bottom: isSource ? undefined : 8 + index * 24,
        color: active ? '#ede9fe' : LOOP_ACCENT,
        background: active ? '#5b21b6' : '#1e1930',
        border: `1px solid ${active ? '#c4b5fd' : '#7c3aed'}`,
        boxShadow: active ? '0 0 0 2px #7c3aed55, 0 4px 12px #0c091666' : '0 2px 8px #0c091655',
      }}
      aria-pressed={selected}
      aria-label={isSource
        ? `Loop ${anchor.label}, feedback source. Open loop details.`
        : `Loop ${anchor.label}, re-entry target. Open loop details.`}
      title={isSource
        ? `Loop ${anchor.label}: feedback starts here`
        : `Loop ${anchor.label}: control re-enters here`}
      onClick={selectLoop}
      onMouseEnter={() => setHoveredLoopCandidateId(anchor.candidateId)}
      onMouseLeave={() => setHoveredLoopCandidateId(null)}
      onFocus={() => setHoveredLoopCandidateId(anchor.candidateId)}
      onBlur={() => setHoveredLoopCandidateId(null)}
    >
      <span className="flex h-5 items-center gap-0.5 rounded-full px-1 font-mono text-[9px] font-bold leading-none" aria-hidden="true">
        {isSource ? (
          <span className="material-symbols-outlined text-[13px]">sync</span>
        ) : null}
        <span>{anchor.label}</span>
        {!isSource ? (
          <span className="material-symbols-outlined text-[13px]">subdirectory_arrow_left</span>
        ) : null}
      </span>
    </button>
  )
}
