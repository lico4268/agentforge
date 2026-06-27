import { Fragment } from 'react'
import { Handle, Position } from '@xyflow/react'
import type { Port } from '@/types'

const HANDLE_STYLE = {
  width: 9,
  height: 9,
  background: '#0b0e14',
  border: '2px solid #64748b',
} as const

/**
 * Input handles distributed across the TOP edge of the node.
 * The section div has position:relative so handles are positioned relative
 * to it — Position.Top gives top:-4px (pokes above section top = node top edge).
 */
export function NodeInputs({ inputs }: { inputs: Port[] }) {
  if (!inputs.length) return null
  const n = inputs.length
  return (
    <div className="relative h-7 border-b border-white/5">
      {inputs.map((p, i) => {
        const left = `${((i + 1) / (n + 1)) * 100}%`
        return (
          <Fragment key={p.id}>
            <Handle
              type="target"
              position={Position.Top}
              id={p.id}
              style={{ ...HANDLE_STYLE, left }}
            />
            <span
              className="absolute bottom-0.5 text-[10px] text-slate-500 select-none pointer-events-none whitespace-nowrap"
              style={{ left, transform: 'translateX(-50%)' }}
            >
              {p.label}
            </span>
          </Fragment>
        )
      })}
    </div>
  )
}

/**
 * Output handles distributed across the BOTTOM edge of the node.
 * Position.Bottom gives bottom:-4px (pokes below section bottom = node bottom edge).
 */
export function NodeOutputs({ outputs }: { outputs: Port[] }) {
  if (!outputs.length) return null
  const n = outputs.length
  return (
    <div className="relative h-7 border-t border-white/5">
      {outputs.map((p, i) => {
        const left = `${((i + 1) / (n + 1)) * 100}%`
        return (
          <Fragment key={p.id}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={p.id}
              style={{ ...HANDLE_STYLE, left }}
            />
            <span
              className="absolute top-0.5 text-[10px] text-slate-500 select-none pointer-events-none whitespace-nowrap"
              style={{ left, transform: 'translateX(-50%)' }}
            >
              {p.label}
            </span>
          </Fragment>
        )
      })}
    </div>
  )
}
