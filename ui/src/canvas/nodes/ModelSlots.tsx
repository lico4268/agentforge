import type { ModelSlot } from '@/types'

const PROVIDER_ICONS: Record<string, string> = {
  anthropic: 'auto_awesome',
  openai:    'psychology',
  google:    'search',
  local:     'computer',
}

function FilledSlot({ slot, accent }: { slot: ModelSlot; accent: string }) {
  return (
    <div
      className="flex items-center gap-2 rounded-md px-2.5 py-2"
      style={{ background: `${accent}10`, border: `1px solid ${accent}35` }}
    >
      <span
        className="material-symbols-outlined shrink-0 rounded-full p-1"
        style={{
          fontSize: 12,
          color: accent,
          background: `${accent}20`,
          fontVariationSettings: "'FILL' 1",
        }}
      >
        {PROVIDER_ICONS[slot.provider] ?? 'smart_toy'}
      </span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[11px] font-semibold text-[#dde4dd]">{slot.model}</span>
        {slot.role && (
          <span className="truncate font-mono text-[9px] text-[#86948a]">{slot.role}</span>
        )}
      </div>
      <span
        className="material-symbols-outlined shrink-0"
        style={{ fontSize: 13, color: '#4edea3', fontVariationSettings: "'FILL' 1" }}
      >
        check_circle
      </span>
    </div>
  )
}

function EmptySlot() {
  return (
    <div
      className="flex items-center justify-center rounded-md py-2"
      style={{
        border: '1px dashed rgba(255,255,255,0.12)',
        background: 'rgba(255,255,255,0.02)',
      }}
    >
      <span className="font-mono text-[9px] uppercase tracking-widest text-[#3c4a42]">
        Empty Slot
      </span>
    </div>
  )
}

interface ModelSlotsSectionProps {
  slots: ModelSlot[]
  maxSlots: number
  accent: string
}

export function ModelSlotsSection({ slots, maxSlots, accent }: ModelSlotsSectionProps) {
  const filledCount = slots.length

  return (
    <div className="mx-2 mb-2 flex flex-col gap-1.5">
      {/* dashed container */}
      <div
        className="flex flex-col gap-1.5 rounded-md p-1.5"
        style={{ border: '1px dashed rgba(255,255,255,0.10)', background: 'rgba(0,0,0,0.2)' }}
      >
        {slots.map((slot) => (
          <FilledSlot key={slot.id} slot={slot} accent={accent} />
        ))}
        {Array.from({ length: maxSlots - filledCount }).map((_, i) => (
          <EmptySlot key={`empty-${i}`} />
        ))}
      </div>

      {/* SLOTS counter */}
      <div className="flex items-center justify-between px-0.5">
        <span className="font-mono text-[9px] uppercase tracking-widest text-[#86948a]">Slots</span>
        <span className="font-mono text-[10px]" style={{ color: accent }}>
          {filledCount} / {maxSlots}
        </span>
      </div>
    </div>
  )
}
