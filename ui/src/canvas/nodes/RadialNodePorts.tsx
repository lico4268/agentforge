import { Fragment } from 'react'
import { Handle } from '@xyflow/react'
import type { Port } from '@/types'
import { useUiStore } from '@/stores/useUiStore'
import { handleStyle, pointFromAngleDeg, positionFromAngleDeg, resolveNodePortAngles } from './radialPortGeometry'
import { useHubRimAngles } from './hubRimAngles'

type PortSide = 'input' | 'output'
type SidedPort = Port & { side: PortSide }

type RadialNodePortsProps = {
  nodeId: string
  inputs: Port[]
  outputs: Port[]
  color?: string
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
export function RadialNodePorts({ nodeId, inputs, outputs, color = '#3c4a42' }: RadialNodePortsProps) {
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const inputAngles = useHubRimAngles(nodeId, inputs, 'input')
  const outputAngles = useHubRimAngles(nodeId, outputs, 'output')

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
