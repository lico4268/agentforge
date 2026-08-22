import { describe, expect, it } from 'vitest'
import type { Edge } from '@xyflow/react'
import { useGraphStore, type RFNode } from '@/stores/useGraphStore'
import { STARTER_ARCHITECTURE } from '@/app/starterArchitecture'
import {
  LOOP_COLLAPSED_NODE_TYPE,
  projectCollapsedView,
  projectDrilledInView,
  type LoopCollapsedNodeData,
} from '@/canvas/loop/loopProjection'

function loadStarterGraph() {
  useGraphStore.getState().loadArchitecture(STARTER_ARCHITECTURE)
  const { nodes, edges } = useGraphStore.getState()
  return { nodes, edges }
}

describe('projectCollapsedView on the starter graph', () => {
  it('hides the loop members and keeps every other node untouched', () => {
    const { nodes, edges } = loadStarterGraph()
    const { nodes: result } = projectCollapsedView(nodes, edges)

    expect(result.map((n) => n.id).sort()).toEqual(
      ['input', 'planning', 'loop_guard', 'human_checkpoint', 'output'].sort(),
    )
  })

  it('turns the guard node into a collapsed node carrying 3 members and the right crossing ports', () => {
    const { nodes, edges } = loadStarterGraph()
    const { nodes: result } = projectCollapsedView(nodes, edges)

    const guard = result.find((n) => n.id === 'loop_guard')!
    expect(guard.type).toBe(LOOP_COLLAPSED_NODE_TYPE)

    const data = guard.data as LoopCollapsedNodeData
    expect(data.memberCount).toBe(3)
    expect(data.memberIds).toEqual(['loop_reentry', 'reasoning', 'review'])
    expect(data.loopInputs.map((p) => p.label)).toEqual(['plan', 'task'])
    expect(data.loopOutputs.map((p) => p.label)).toEqual(['accept', 'clarify', 'exit'])
  })

  it('drops the 4 internal edges and reroutes the 5 boundary-crossing edges onto the guard, leaving the 2 fully-external edges untouched', () => {
    const { nodes, edges } = loadStarterGraph()
    const { edges: result } = projectCollapsedView(nodes, edges)

    expect(result).toHaveLength(7)
    expect(result.find((e) => e.id === 'e4')).toBeUndefined() // reasoning -> review, internal
    expect(result.find((e) => e.id === 'e6')).toBeUndefined() // review -> loop_guard, internal
    expect(result.find((e) => e.id === 'e9')).toBeUndefined() // loop_guard -> loop_reentry, internal
    expect(result.find((e) => e.id === 'e11')).toBeUndefined() // loop_reentry -> reasoning, internal

    const e2 = result.find((e) => e.id === 'e2')!
    expect(e2).toMatchObject({ source: 'planning', target: 'loop_guard', targetHandle: 'e2' })

    const e5 = result.find((e) => e.id === 'e5')!
    expect(e5).toMatchObject({ source: 'loop_guard', target: 'output', sourceHandle: 'e5' })
    expect(e5.data).toMatchObject({ branchHandle: 'accept' })

    const e1 = result.find((e) => e.id === 'e1')!
    expect(e1).toMatchObject({ source: 'input', target: 'planning' }) // untouched passthrough
  })

  it('is a no-op when there is no loop.guard node at all', () => {
    const { nodes: starterNodes } = loadStarterGraph()
    const nodes = starterNodes.filter((n) => n.data.manifestType !== 'loop.guard')
    const edges: Edge[] = []
    expect(projectCollapsedView(nodes, edges)).toEqual({ nodes, edges })
  })
})

describe('projectCollapsedView with two independent loops', () => {
  const nodes: RFNode[] = [
    { id: 'src', type: 'io.input', position: { x: 0, y: 0 }, data: { manifestType: 'io.input', config: {} } },
    { id: 'mid1', type: 'reasoning.cot', position: { x: 100, y: 0 }, data: { manifestType: 'reasoning.cot', config: {} } },
    { id: 'guard1', type: 'loop.guard', position: { x: 200, y: 0 }, data: { manifestType: 'loop.guard', config: {} } },
    { id: 'mid2', type: 'reasoning.cot', position: { x: 300, y: 0 }, data: { manifestType: 'reasoning.cot', config: {} } },
    { id: 'guard2', type: 'loop.guard', position: { x: 400, y: 0 }, data: { manifestType: 'loop.guard', config: {} } },
    { id: 'sink', type: 'io.output', position: { x: 500, y: 0 }, data: { manifestType: 'io.output', config: {} } },
  ]
  const edges: Edge[] = [
    { id: 'e1', source: 'src', sourceHandle: 'task', target: 'mid1' },
    { id: 'e2', source: 'mid1', sourceHandle: 'refine', target: 'guard1' },
    { id: 'e3', source: 'guard1', sourceHandle: 'loopBack', target: 'mid1' },
    { id: 'e4', source: 'guard1', sourceHandle: 'exit', target: 'mid2' },
    { id: 'e5', source: 'mid2', sourceHandle: 'refine', target: 'guard2' },
    { id: 'e6', source: 'guard2', sourceHandle: 'loopBack', target: 'mid2' },
    { id: 'e7', source: 'guard2', sourceHandle: 'exit', target: 'sink' },
  ]

  it('collapses both loops independently and correctly labels the edge chaining them together', () => {
    const { nodes: resultNodes, edges: resultEdges } = projectCollapsedView(nodes, edges)

    expect(resultNodes.map((n) => n.id).sort()).toEqual(['guard1', 'guard2', 'sink', 'src'].sort())

    const guard1 = resultNodes.find((n) => n.id === 'guard1')!.data as LoopCollapsedNodeData
    expect(guard1.memberCount).toBe(1)
    expect(guard1.loopInputs.map((p) => p.label)).toEqual(['task'])
    expect(guard1.loopOutputs.map((p) => p.label)).toEqual(['exit']) // e4, chained straight into guard2

    const guard2 = resultNodes.find((n) => n.id === 'guard2')!.data as LoopCollapsedNodeData
    expect(guard2.memberCount).toBe(1)
    expect(guard2.loopInputs.map((p) => p.label)).toEqual(['exit']) // same e4, from guard2's side
    expect(guard2.loopOutputs.map((p) => p.label)).toEqual(['exit']) // e7

    const chainEdge = resultEdges.find((e) => e.id === 'e4')!
    expect(chainEdge).toMatchObject({ source: 'guard1', sourceHandle: 'e4', target: 'guard2', targetHandle: 'e4' })
  })
})

describe('projectDrilledInView on the starter graph', () => {
  it('shows only the guard and its members, and only the edges between them', () => {
    const { nodes, edges } = loadStarterGraph()
    const { nodes: viewNodes, edges: viewEdges } = projectDrilledInView(nodes, edges, 'loop_guard')

    expect(viewNodes.map((n) => n.id).sort()).toEqual(
      ['loop_guard', 'loop_reentry', 'reasoning', 'review'].sort(),
    )
    expect(viewEdges.map((e) => e.id).sort()).toEqual(['e4', 'e6', 'e9', 'e11'].sort())
  })

  it('is a no-op on nodes/edges when the guard has no loopBack target', () => {
    const { nodes: starterNodes, edges: starterEdges } = loadStarterGraph()
    const edges = starterEdges.filter((e) => !(e.source === 'loop_guard' && e.sourceHandle === 'loopBack'))
    const { nodes: viewNodes } = projectDrilledInView(starterNodes, edges, 'loop_guard')

    expect(viewNodes.map((n) => n.id).sort()).toEqual(['loop_guard'].sort())
  })
})
