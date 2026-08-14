import { Fragment } from 'react'
import { Handle } from '@xyflow/react'
import type { Port } from '@/types'
import { useUiStore } from '@/stores/useUiStore'
import { handleStyle, pointFromAngleDeg, positionFromAngleDeg, resolveNodePortAngles } from './radialPortGeometry'
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
 * Renders every port (input and output together) on one shared 360-degree
 * pool around the node's boundary — there is no hemisphere split anymore.
 * Direction is read from the edge's arrowhead, not from which side a port
 * sits on, so a port is free to sit wherever its real partner actually is.
 * Dots are hidden by default (`useUiStore.showConnectionPorts`) — connection
 * meaning lives on the edge's label, and dots only reappear while the user
 * is actively wiring up new connections.
 */
export function RadialNodePorts({ nodeId, inputs, outputs, color = '#3c4a42', viewOverride }: RadialNodePortsProps) {
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
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
  const rimAngleDeg = inputAngles.rimAngleDeg

  const angles = resolveNodePortAngles(
    ports.map((port) => ({ partnerAngleDeg: partnerAngleDegByPortId[port.id] })),
    rimAngleDeg,
  )

  return (
    <>
      {ports.map((port, index) => {
        const angle = angles[index]
        const isInput = port.side === 'input'
        return (
          <Fragment key={`${port.side}:${port.id}`}>
            <Handle
              type={isInput ? 'target' : 'source'}
              position={positionFromAngleDeg(angle)}
              id={port.id}
              style={{
                ...handleStyle(color, showConnectionPorts),
                ...pointFromAngleDeg(angle),
                transform: 'translate(-50%, -50%)',
              }}
              title={`${isInput ? 'Input' : 'Output'}: ${port.label}`}
              aria-label={`${isInput ? 'Input' : 'Output'} port: ${port.label}`}
            />
          </Fragment>
        )
      })}
    </>
  )
}
