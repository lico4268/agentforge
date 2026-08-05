import { useState } from 'react'
import type { LoopCandidateView } from './loops/loopAnchors'

type Props = {
  candidates: LoopCandidateView[]
  selectedCandidateId: string | null
  labelByNodeId: Map<string, string>
  onSelect: (candidateId: string) => void
}

export function LoopControlPanel({ candidates, selectedCandidateId, labelByNodeId, onSelect }: Props) {
  const [open, setOpen] = useState(false)

  if (candidates.length === 0) return null

  return (
    <div className="w-52 rounded-lg border border-[#4c3a75] bg-[#161d19]/95 p-1 shadow-xl backdrop-blur">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[10px] font-semibold text-[#ddd6fe] transition-colors hover:bg-[#7c3aed]/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ddd6fe]"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[14px] text-[#a78bfa]" aria-hidden="true">sync</span>
          Loops {candidates.length}
        </span>
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {open && (
        <div className="mt-1 flex max-h-52 flex-col gap-1 overflow-y-auto border-t border-[#4c3a75]/60 pt-1">
          {candidates.map((candidate) => {
            const selected = selectedCandidateId === candidate.id
            const members = candidate.memberNodeIds
              .map((nodeId) => labelByNodeId.get(nodeId) ?? nodeId)
              .join(' · ')
            return (
              <button
                key={candidate.id}
                type="button"
                onClick={() => onSelect(candidate.id)}
                aria-pressed={selected}
                className="rounded-md px-2.5 py-2 text-left transition-colors hover:bg-[#7c3aed]/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ddd6fe]"
                style={{ background: selected ? '#7c3aed22' : undefined }}
              >
                <span className="flex items-center justify-between gap-2 font-mono text-[10px] font-semibold text-[#ddd6fe]">
                  <span>{candidate.label}</span>
                  <span className="rounded border border-[#a78bfa]/40 px-1 py-px text-[8px] text-[#c4b5fd]">Candidate</span>
                </span>
                <span className="mt-0.5 block truncate text-[9px] text-[#a99fbc]">{members}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
