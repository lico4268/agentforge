import { describe, expect, it } from 'vitest'
import { computeHubRimAngles } from '@/canvas/nodes/hubRimAngles'

const nodes = [
  { id: 'center', position: { x: 0, y: 0 } },
  { id: 'east', position: { x: 200, y: 0 } },
  { id: 'north', position: { x: 0, y: -200 } },
  { id: 'partner', position: { x: 200, y: -200 } },
]

describe('computeHubRimAngles', () => {
  it('falls back to rimAngleDeg 0 with no partners when there is no radial center', () => {
    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }],
      side: 'input',
      radialCenterId: null,
      nodes,
      edges: [],
    })

    expect(result).toEqual({ rimAngleDeg: 0, partnerAngleDegByPortId: {} })
  })

  it('falls back to rimAngleDeg 0 when this node is itself the radial center', () => {
    const result = computeHubRimAngles({
      nodeId: 'center',
      ports: [{ id: 'task' }],
      side: 'input',
      radialCenterId: 'center',
      nodes,
      edges: [],
    })

    expect(result).toEqual({ rimAngleDeg: 0, partnerAngleDegByPortId: {} })
  })

  it('computes rimAngleDeg as the direction from the radial center to this node', () => {
    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [],
      side: 'output',
      radialCenterId: 'center',
      nodes,
      edges: [],
    })

    // 'east' sits directly to the right of 'center' -> rim direction is 0deg
    expect(result.rimAngleDeg).toBeCloseTo(0)
  })

  it('computes a different rimAngleDeg for a node placed above the center', () => {
    const result = computeHubRimAngles({
      nodeId: 'north',
      ports: [],
      side: 'output',
      radialCenterId: 'center',
      nodes,
      edges: [],
    })

    // 'north' sits directly above 'center' on screen -> rim direction is 90deg
    expect(result.rimAngleDeg).toBeCloseTo(90)
  })

  it('resolves an output port\'s partner angle from the edge target position', () => {
    const edges = [{ source: 'east', sourceHandle: 'answer', target: 'partner', targetHandle: 'task' }]

    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'answer' }],
      side: 'output',
      radialCenterId: 'center',
      nodes,
      edges,
    })

    // 'partner' sits directly above 'east' (same x, smaller y) -> 90deg
    expect(result.partnerAngleDegByPortId.answer).toBeCloseTo(90)
  })

  it('resolves an input port\'s partner angle from the edge source position', () => {
    const edges = [{ source: 'partner', sourceHandle: 'answer', target: 'east', targetHandle: 'task' }]

    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }],
      side: 'input',
      radialCenterId: 'center',
      nodes,
      edges,
    })

    expect(result.partnerAngleDegByPortId.task).toBeCloseTo(90)
  })

  it('omits a port from partnerAngleDegByPortId when it has no connected edge', () => {
    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }, { id: 'model' }],
      side: 'input',
      radialCenterId: 'center',
      nodes,
      edges: [{ source: 'north', sourceHandle: 'plan', target: 'east', targetHandle: 'task' }],
    })

    expect(result.partnerAngleDegByPortId).toHaveProperty('task')
    expect(result.partnerAngleDegByPortId).not.toHaveProperty('model')
  })

  it('ignores edges on the other side (wrong handle direction)', () => {
    // an edge where 'east' is the target should not count as an output partner
    const edges = [{ source: 'north', sourceHandle: 'plan', target: 'east', targetHandle: 'task' }]

    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }],
      side: 'output',
      radialCenterId: 'center',
      nodes,
      edges,
    })

    expect(result.partnerAngleDegByPortId).toEqual({})
  })

  it('still resolves partner angles when there is no radial center', () => {
    const edges = [{ source: 'partner', sourceHandle: 'answer', target: 'east', targetHandle: 'task' }]

    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }],
      side: 'input',
      radialCenterId: null,
      nodes,
      edges,
    })

    expect(result.rimAngleDeg).toBe(0)
    expect(result.partnerAngleDegByPortId.task).toBeCloseTo(90)
  })

  it('still resolves partner angles when this node is itself the radial center', () => {
    const edges = [{ source: 'partner', sourceHandle: 'answer', target: 'east', targetHandle: 'task' }]

    const result = computeHubRimAngles({
      nodeId: 'east',
      ports: [{ id: 'task' }],
      side: 'input',
      radialCenterId: 'east',
      nodes,
      edges,
    })

    expect(result.rimAngleDeg).toBe(0)
    expect(result.partnerAngleDegByPortId.task).toBeCloseTo(90)
  })
})
