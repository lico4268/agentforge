import { create } from 'zustand'
import {
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react'
import type { Architecture, GraphNode } from '@/types'

/**
 * Topology store — the design the user draws. Source of truth for nodes/edges/
 * config and selection. Deliberately separate from execution state so editing
 * and the high-frequency event stream never contend. See ui-architecture.md §2.
 *
 * React Flow node `data` carries `{ type, config }`; `node.type` is the
 * manifest type so the registry-built nodeTypes map resolves the renderer.
 */
export type RFNodeData = {
  manifestType: string
  config: Record<string, unknown>
}
export type RFNode = Node<RFNodeData>

type GraphState = {
  nodes: RFNode[]
  edges: Edge[]
  selectedNodeId: string | null

  onNodesChange: (changes: NodeChange<RFNode>[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void

  addNode: (manifestType: string, position: { x: number; y: number }, config?: Record<string, unknown>) => void
  updateNodeConfig: (id: string, config: Record<string, unknown>) => void
  select: (id: string | null) => void

  loadArchitecture: (arch: Architecture) => void
  toArchitecture: (name: string) => Architecture
}

let seq = 0
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${seq++}`

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),
  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),
  onConnect: (connection) => set({ edges: addEdge(connection, get().edges) }),

  addNode: (manifestType, position, config = {}) =>
    set((s) => ({
      nodes: [
        ...s.nodes,
        {
          id: nextId('n'),
          type: manifestType,
          position,
          data: { manifestType, config },
        },
      ],
    })),

  updateNodeConfig: (id, config) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, config } } : n,
      ),
    })),

  select: (id) => set({ selectedNodeId: id }),

  loadArchitecture: (arch) =>
    set({
      nodes: arch.nodes.map((n: GraphNode) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: { manifestType: n.type, config: n.config },
      })),
      edges: arch.edges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle,
        target: e.target,
        targetHandle: e.targetHandle,
      })),
      selectedNodeId: null,
    }),

  toArchitecture: (name) => {
    const { nodes, edges } = get()
    return {
      version: '0.1',
      metadata: { name, createdAt: new Date().toISOString() },
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.data.manifestType,
        position: n.position,
        config: n.data.config,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle ?? 'out',
        target: e.target,
        targetHandle: e.targetHandle ?? 'in',
      })),
    }
  },
}))
