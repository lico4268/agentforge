import type { Edge } from '@xyflow/react'
import type { RFNode, RFNodeData } from '@/stores/useGraphStore'
import { deriveLoopMembers } from './deriveLoopMembers'

/** Synthetic React Flow node type for a collapsed loop, registered in
 * `Canvas.tsx`'s `nodeTypes` map alongside the real manifest-driven types. */
export const LOOP_COLLAPSED_NODE_TYPE = '__loopCollapsed__'

/** One materialized port per boundary-crossing edge — no attempt to merge
 * same-named handles into one port, so the dot count on the collapsed node
 * always matches the real fan-in/fan-out count. */
export type CrossingPort = { id: string; label: string; dataType: string }

export type LoopCollapsedNodeData = RFNodeData & {
  loopNodeId: string
  memberCount: number
  /** Node ids collapsed into this loop — lets consumers (e.g. LoopNode's
   * pending-checkpoint badge) scope graph-wide state to just this loop's
   * members instead of reacting to any node anywhere in the graph. */
  memberIds: string[]
  loopInputs: CrossingPort[]
  loopOutputs: CrossingPort[]
  /** Just enough of the projected view for RadialNodePorts' partner-angle
   * bias to work on this node's synthetic ports: the rerouted edges that
   * touch it, plus the position of every node those edges touch. */
  portView: { nodes: { id: string; position: { x: number; y: number } }[]; edges: Edge[] }
}

function isLoopGuard(node: RFNode): boolean {
  return node.data.manifestType === 'loop.guard'
}

function crossingPort(edge: Edge): CrossingPort {
  return { id: edge.id, label: edge.sourceHandle ?? edge.id, dataType: 'any' }
}

/**
 * Main-canvas view: every `loop.guard` node with a wired `loopBack` edge
 * collapses its member nodes (see deriveLoopMembers) into itself. Pure —
 * never mutates the graph store, only returns new arrays for React Flow to
 * render (spec: "Loop 표현은 순수 캔버스 view-layer 투영이다").
 */
export function projectCollapsedView(
  nodes: RFNode[],
  edges: Edge[],
): { nodes: RFNode[]; edges: Edge[] } {
  const nodeIds = nodes.map((n) => n.id)
  const loopGuards = nodes.filter(isLoopGuard)

  const memberSetByLoop = new Map<string, Set<string>>()
  for (const guard of loopGuards) {
    const members = new Set(deriveLoopMembers(nodeIds, edges, guard.id))
    if (members.size > 0) memberSetByLoop.set(guard.id, members)
  }
  if (memberSetByLoop.size === 0) return { nodes, edges }

  // Which loop "owns" a node id: a guard owns itself, a member is owned by
  // its guard. A node can only belong to one loop — nested loops can't arise
  // from a valid compiled graph (see this plan's Global Constraints).
  const ownerOf = new Map<string, string>()
  for (const [loopId, members] of memberSetByLoop) {
    ownerOf.set(loopId, loopId)
    for (const memberId of members) ownerOf.set(memberId, loopId)
  }

  const loopInputsById = new Map<string, CrossingPort[]>()
  const loopOutputsById = new Map<string, CrossingPort[]>()
  for (const loopId of memberSetByLoop.keys()) {
    loopInputsById.set(loopId, [])
    loopOutputsById.set(loopId, [])
  }

  const rerouted: Edge[] = []
  const passthrough: Edge[] = []

  for (const edge of edges) {
    const sourceOwner = ownerOf.get(edge.source)
    const targetOwner = ownerOf.get(edge.target)

    if (sourceOwner && sourceOwner === targetOwner) {
      continue // internal to one loop — hidden while collapsed
    } else if (!sourceOwner && targetOwner) {
      loopInputsById.get(targetOwner)!.push(crossingPort(edge))
      rerouted.push({ ...edge, target: targetOwner, targetHandle: edge.id })
    } else if (sourceOwner && !targetOwner) {
      loopOutputsById.get(sourceOwner)!.push(crossingPort(edge))
      rerouted.push({
        ...edge,
        source: sourceOwner,
        sourceHandle: edge.id,
        data: { ...edge.data, branchHandle: edge.sourceHandle },
      })
    } else if (sourceOwner && targetOwner) {
      // Chains straight from one loop into another (e.g. guard1's exit feeds
      // guard2's member directly) — reroute both ends onto their own guard.
      loopOutputsById.get(sourceOwner)!.push(crossingPort(edge))
      loopInputsById.get(targetOwner)!.push(crossingPort(edge))
      rerouted.push({
        ...edge,
        source: sourceOwner,
        sourceHandle: edge.id,
        target: targetOwner,
        targetHandle: edge.id,
        data: { ...edge.data, branchHandle: edge.sourceHandle },
      })
    } else {
      passthrough.push(edge)
    }
  }

  const resultNodes: RFNode[] = nodes
    .filter((n) => {
      const owner = ownerOf.get(n.id)
      return owner === undefined || owner === n.id // keep: not in any loop, or is the loop's own guard
    })
    .map((n) => {
      const members = memberSetByLoop.get(n.id)
      if (!members) return n

      const touchingRerouted = rerouted.filter((e) => e.source === n.id || e.target === n.id)
      const portViewIds = new Set<string>([n.id, ...touchingRerouted.flatMap((e) => [e.source, e.target])])

      const data: LoopCollapsedNodeData = {
        ...n.data,
        loopNodeId: n.id,
        memberCount: members.size,
        memberIds: [...members],
        loopInputs: loopInputsById.get(n.id) ?? [],
        loopOutputs: loopOutputsById.get(n.id) ?? [],
        portView: {
          nodes: nodes.filter((p) => portViewIds.has(p.id)).map((p) => ({ id: p.id, position: p.position })),
          edges: touchingRerouted,
        },
      }
      return { ...n, type: LOOP_COLLAPSED_NODE_TYPE, data }
    })

  return { nodes: resultNodes, edges: [...passthrough, ...rerouted] }
}

/**
 * Drilled-in view for one specific loop: only that loop's guard and its
 * members, with only the edges that run between them. Everything else in the
 * graph — including other loops — is out of frame entirely; this is full
 * navigation, not an in-place expansion (spec §3).
 */
export function projectDrilledInView(
  nodes: RFNode[],
  edges: Edge[],
  loopNodeId: string,
): { nodes: RFNode[]; edges: Edge[] } {
  const members = deriveLoopMembers(nodes.map((n) => n.id), edges, loopNodeId)
  const visible = new Set([loopNodeId, ...members])

  return {
    nodes: nodes.filter((n) => visible.has(n.id)),
    edges: edges.filter((e) => visible.has(e.source) && visible.has(e.target)),
  }
}
