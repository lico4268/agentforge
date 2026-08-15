import { Fragment, useState } from 'react'
import { Handle, useConnection } from '@xyflow/react'
import type { Port } from '@/types'
import { useUiStore } from '@/stores/useUiStore'
import {
  connectedHandleStyle,
  labelPointFromAngleDeg,
  pointFromAngleDeg,
  positionFromAngleDeg,
  resolveNodePortAngles,
  revealableHandleStyle,
  unconnectedPortAngles,
} from './radialPortGeometry'
import { computeHubRimAngles, useHubRimAngles, type HubRimAngles } from './hubRimAngles'

type PortSide = 'input' | 'output'
type SidedPort = Port & { side: PortSide }

type ViewOverride = {
  nodes: { id: string; position: { x: number; y: number } }[]
  edges: { source: string; sourceHandle?: string | null; target: string; targetHandle?: string | null }[]
  radialCenterId: string | null
}

type RadialNodePortsProps = {
  nodeId: string
  inputs: Port[]
  outputs: Port[]
  color?: string
  /** Bypasses the live graph-store subscription and computes partner angles
   * against this projected view instead. Used by the collapsed loop node,
   * whose ports are synthetic (rerouted crossing edges, see
   * `canvas/loop/loopProjection.ts`) and don't exist in the raw store's edge
   * list. Real canvas nodes omit this and read live from the store, exactly
   * as before this prop existed. */
  viewOverride?: ViewOverride
}

/**
 * Renders every port around the node's full 360-degree boundary. Connected
 * ports never draw a visible dot — the edge line already shows exactly
 * where they attach (see radialPortGeometry.ts's connectedHandleStyle).
 * Unconnected ports draw nothing until the node is hovered in connection
 * edit mode, at which point they appear clustered near a default direction
 * (inputs hub-facing, outputs rim-facing) instead of claiming a permanent
 * slot on the circle.
 */
export function RadialNodePorts({ nodeId, inputs, outputs, color = '#3c4a42', viewOverride }: RadialNodePortsProps) {
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const [isHovered, setIsHovered] = useState(false)
  const connectionInProgress = useConnection((c) => c.inProgress)
  const liveInputAngles = useHubRimAngles(nodeId, inputs, 'input')
  const liveOutputAngles = useHubRimAngles(nodeId, outputs, 'output')

  const inputAngles: HubRimAngles = viewOverride
    ? computeHubRimAngles({ nodeId, ports: inputs, side: 'input', ...viewOverride })
    : liveInputAngles
  const outputAngles: HubRimAngles = viewOverride
    ? computeHubRimAngles({ nodeId, ports: outputs, side: 'output', ...viewOverride })
    : liveOutputAngles

  const ports: SidedPort[] = [
    ...inputs.map((port) => ({ ...port, side: 'input' as const })),
    ...outputs.map((port) => ({ ...port, side: 'output' as const })),
  ]
  if (ports.length === 0) return null

  const partnerAngleDegByPortId = {
    ...inputAngles.partnerAngleDegByPortId,
    ...outputAngles.partnerAngleDegByPortId,
  }
  // rimAngleDeg doesn't depend on `side` or the port list — both calls above
  // always agree, so either is fine to use here.
  const seamAngleDeg = inputAngles.rimAngleDeg

  const connectedPorts = ports.filter((port) => partnerAngleDegByPortId[port.id] !== undefined)
  const unconnectedInputs = inputs.filter((port) => partnerAngleDegByPortId[port.id] === undefined)
  const unconnectedOutputs = outputs.filter((port) => partnerAngleDegByPortId[port.id] === undefined)

  const connectedAngles = resolveNodePortAngles(
    connectedPorts.map((port) => ({ partnerAngleDeg: partnerAngleDegByPortId[port.id] })),
    seamAngleDeg,
  )
  const { inputAngles: unconnectedInputAngles, outputAngles: unconnectedOutputAngles } = unconnectedPortAngles(
    unconnectedInputs.length,
    unconnectedOutputs.length,
    seamAngleDeg,
  )

  const revealed = showConnectionPorts && (isHovered || connectionInProgress)

  return (
    <>
      <div
        className="absolute inset-0 rounded-full"
        style={{ pointerEvents: 'auto' }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-hidden="true"
      />
      {connectedPorts.map((port, index) => (
        <Handle
          key={`connected:${port.side}:${port.id}`}
          type={port.side === 'input' ? 'target' : 'source'}
          position={positionFromAngleDeg(connectedAngles[index])}
          id={port.id}
          style={{
            ...connectedHandleStyle(),
            ...pointFromAngleDeg(connectedAngles[index]),
            transform: 'translate(-50%, -50%)',
          }}
          title={`${port.side === 'input' ? 'Input' : 'Output'}: ${port.label}`}
          aria-label={`${port.side === 'input' ? 'Input' : 'Output'} port: ${port.label}`}
        />
      ))}
      {unconnectedInputs.map((port, index) => {
        const angle = unconnectedInputAngles[index]
        return (
          <Fragment key={`unconnected:input:${port.id}`}>
            <Handle
              type="target"
              position={positionFromAngleDeg(angle)}
              id={port.id}
              style={{
                ...revealableHandleStyle(color, revealed),
                ...pointFromAngleDeg(angle),
                transform: 'translate(-50%, -50%)',
              }}
              title={`Input: ${port.label}`}
              aria-label={`Input port: ${port.label}`}
            />
            {revealed && (
              <div
                className="pointer-events-none absolute whitespace-nowrap rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold text-[#dde4dd] shadow-sm"
                style={{ ...labelPointFromAngleDeg(angle), transform: 'translate(-50%, -50%)' }}
              >
                {port.label}
              </div>
            )}
          </Fragment>
        )
      })}
      {unconnectedOutputs.map((port, index) => {
        const angle = unconnectedOutputAngles[index]
        return (
          <Fragment key={`unconnected:output:${port.id}`}>
            <Handle
              type="source"
              position={positionFromAngleDeg(angle)}
              id={port.id}
              style={{
                ...revealableHandleStyle(color, revealed),
                ...pointFromAngleDeg(angle),
                transform: 'translate(-50%, -50%)',
              }}
              title={`Output: ${port.label}`}
              aria-label={`Output port: ${port.label}`}
            />
            {revealed && (
              <div
                className="pointer-events-none absolute whitespace-nowrap rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold text-[#dde4dd] shadow-sm"
                style={{ ...labelPointFromAngleDeg(angle), transform: 'translate(-50%, -50%)' }}
              >
                {port.label}
              </div>
            )}
          </Fragment>
        )
      })}
    </>
  )
}
