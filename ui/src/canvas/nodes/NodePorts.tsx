import { Fragment } from 'react'
import { Handle, Position } from '@xyflow/react'
import type { Port } from '@/types'

function handleStyle(color: string) {
  return {
    width: 9,
    height: 9,
    background: '#0e1511',
    border: `2px solid ${color}`,
    borderRadius: '50%',
  } as const
}

export function NodeInputs({ inputs, color = '#3c4a42' }: { inputs: Port[]; color?: string }) {
  if (!inputs.length) return null
  const n = inputs.length
  return (
    <div className="relative h-6 border-b border-[#3c4a42]/40">
      {inputs.map((p, i) => {
        const left = `${((i + 1) / (n + 1)) * 100}%`
        return (
          <Fragment key={p.id}>
            <Handle
              type="target"
              position={Position.Top}
              id={p.id}
              style={{ ...handleStyle(color), left }}
            />
            <span
              className="pointer-events-none absolute bottom-0.5 select-none whitespace-nowrap font-mono text-[9px] text-[#86948a]"
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

export function NodeOutputs({ outputs, color = '#3c4a42' }: { outputs: Port[]; color?: string }) {
  if (!outputs.length) return null
  const n = outputs.length
  return (
    <div className="relative h-6 border-t border-[#3c4a42]/40">
      {outputs.map((p, i) => {
        const left = `${((i + 1) / (n + 1)) * 100}%`
        return (
          <Fragment key={p.id}>
            <Handle
              type="source"
              position={Position.Bottom}
              id={p.id}
              style={{ ...handleStyle(color), left }}
            />
            <span
              className="pointer-events-none absolute top-0.5 select-none whitespace-nowrap font-mono text-[9px] text-[#86948a]"
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
