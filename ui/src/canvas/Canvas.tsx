import { useCallback, useEffect, useMemo, useRef, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  useReactFlow,
  useNodesInitialized,
  type NodeTypes,
  type EdgeTypes,
} from '@xyflow/react'
import { useShallow } from 'zustand/react/shallow'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { GenericNode } from './nodes/GenericNode'
import { AgentNode } from './nodes/AgentNode'
import { LoopNode } from './nodes/LoopNode'
import { AgentEdge } from './edges/AgentEdge'
import { radialLayout } from './layout/radialLayout'
import { prefersReducedMotion, viewportTransitionDuration } from './viewport'
import { DRAG_MIME } from './dragTypes'
import { LOOP_COLLAPSED_NODE_TYPE, projectCollapsedView, projectDrilledInView } from './loop/loopProjection'

/**
 * The canvas. `nodeTypes` is built from the registry — every manifest type maps
 * to its custom component or GenericNode — so the editor never hardcodes node
 * components. See ui-architecture.md §5.
 */
export function Canvas() {
  const registry = useRegistry()
  const { screenToFlowPosition, fitView } = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const hasFittedInitially = useRef(false)
  const canvasNodeMode = useUiStore((s) => s.canvasNodeMode)
  const setCanvasNodeMode = useUiStore((s) => s.setCanvasNodeMode)
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const toggleConnectionPorts = useUiStore((s) => s.toggleConnectionPorts)
  const drilledInLoopId = useUiStore((s) => s.drilledInLoopId)
  const exitLoop = useUiStore((s) => s.exitLoop)

  // Fit once after React Flow has measured nodes. Panel resizes must preserve
  // the user's viewport, so they intentionally do not trigger another fit.
  useEffect(() => {
    if (!nodesInitialized || hasFittedInitially.current) return
    const frame = requestAnimationFrame(() => {
      hasFittedInitially.current = true
      void fitView({
        padding: 0.2,
        duration: viewportTransitionDuration(prefersReducedMotion()),
      })
    })
    return () => cancelAnimationFrame(frame)
  }, [fitView, nodesInitialized])

  const {
    nodes,
    edges,
    selectedNodeId,
    lastLayoutPositions,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    select,
    applyNodePositions,
    undoLastLayout,
  } =
    useGraphStore(
      useShallow((s) => ({
        nodes: s.nodes,
        edges: s.edges,
        selectedNodeId: s.selectedNodeId,
        lastLayoutPositions: s.lastLayoutPositions,
        onNodesChange: s.onNodesChange,
        onEdgesChange: s.onEdgesChange,
        onConnect: s.onConnect,
        addNode: s.addNode,
        select: s.select,
        applyNodePositions: s.applyNodePositions,
        undoLastLayout: s.undoLastLayout,
      })),
    )

  // Auto-recover if the drilled-into loop's guard node no longer exists in
  // the graph (e.g. it was deleted) while the user was inside it.
  useEffect(() => {
    if (drilledInLoopId && !nodes.some((n) => n.id === drilledInLoopId)) {
      exitLoop()
    }
  }, [drilledInLoopId, nodes, exitLoop])

  const { nodes: viewNodes, edges: viewEdges } = useMemo(() => {
    if (canvasNodeMode !== 'agent') return { nodes, edges }
    if (drilledInLoopId && nodes.some((n) => n.id === drilledInLoopId)) {
      return projectDrilledInView(nodes, edges, drilledInLoopId)
    }
    return projectCollapsedView(nodes, edges)
  }, [nodes, edges, drilledInLoopId, canvasNodeMode])

  // Re-fit whenever the drilled-in loop changes (entering, exiting, or
  // switching between loops) — the visible node set is a completely
  // different subgraph each time, unlike a panel resize.
  const previousDrilledInLoopId = useRef(drilledInLoopId)
  useEffect(() => {
    if (previousDrilledInLoopId.current === drilledInLoopId) return
    if (!nodesInitialized) return
    previousDrilledInLoopId.current = drilledInLoopId
    const frame = requestAnimationFrame(() => {
      void fitView({ padding: 0.2, duration: viewportTransitionDuration(prefersReducedMotion()) })
    })
    return () => cancelAnimationFrame(frame)
  }, [drilledInLoopId, fitView, nodesInitialized])

  const nodeTypes: NodeTypes = useMemo(() => {
    const map: NodeTypes = {}
    for (const m of registry.all()) {
      map[m.type] = registry.customComponent(m.type) ?? (canvasNodeMode === 'agent' ? AgentNode : GenericNode)
    }
    map[LOOP_COLLAPSED_NODE_TYPE] = LoopNode
    return map
  }, [canvasNodeMode, registry])
  const edgeTypes: EdgeTypes = useMemo(() => ({ agent: AgentEdge }), [])
  const renderedEdges = useMemo(
    () =>
      canvasNodeMode === 'agent'
        ? viewEdges.map((edge) => ({ ...edge, type: 'agent' }))
        : viewEdges,
    [canvasNodeMode, viewEdges],
  )

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      const manifestType = e.dataTransfer.getData(DRAG_MIME)
      if (!manifestType) return
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      addNode(manifestType, position)
    },
    [screenToFlowPosition, addNode],
  )

  // Arrange radially still operates on the raw graph (not the collapsed/
  // drilled-in view) — rearranging a loop's hidden members while it's
  // collapsed is a real but low-priority gap, left for a follow-up.
  const arrangeRadially = useCallback(() => {
    const centerNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0]
    if (!centerNode) return
    applyNodePositions(radialLayout(nodes, edges, { centerId: centerNode.id }), centerNode.id)
    requestAnimationFrame(() => {
      void fitView({
        padding: 0.24,
        duration: viewportTransitionDuration(prefersReducedMotion()),
      })
    })
  }, [applyNodePositions, edges, fitView, nodes, selectedNodeId])

  return (
    <div className="h-full w-full bg-[#0e1511]">
      <ReactFlow
        nodes={viewNodes}
        edges={renderedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={(_, node) => select(node.id)}
        onPaneClick={() => select(null)}
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(255,255,255,0.07)" />
        <Controls className="!rounded-lg !border-[#3c4a42] !bg-[#161d19]/90 backdrop-blur" />
        <MiniMap
          pannable
          zoomable
          className="!rounded-lg !border-[#3c4a42] !bg-[#161d19]/90"
          nodeColor={(n) => {
            const m = registry.get((n.data as { manifestType: string }).manifestType)
            return m ? CATEGORY_META[m.category].color : '#475569'
          }}
        />
        <Panel position="top-right" className="!m-3 flex flex-col items-end gap-2">
          <div className="flex rounded-lg border border-[#3c4a42] bg-[#161d19]/90 p-1 text-[10px] font-semibold backdrop-blur">
            {(['classic', 'agent'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setCanvasNodeMode(mode)}
                aria-pressed={canvasNodeMode === mode}
                className="rounded-md px-2.5 py-1 uppercase tracking-wide transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
                style={{
                  background: canvasNodeMode === mode ? '#4edea322' : 'transparent',
                  color: canvasNodeMode === mode ? '#4edea3' : '#86948a',
                }}
              >
                {mode}
              </button>
            ))}
          </div>
          {canvasNodeMode === 'agent' && (
            <button
              type="button"
              onClick={toggleConnectionPorts}
              aria-pressed={showConnectionPorts}
              title="Show connection ports to drag new edges — hidden by default so direction reads from the arrowhead"
              className="flex items-center gap-1 rounded-lg border border-[#3c4a42] bg-[#161d19]/90 px-2.5 py-1 text-[10px] font-semibold backdrop-blur transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
              style={{ color: showConnectionPorts ? '#4edea3' : '#86948a' }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                {showConnectionPorts ? 'toggle_on' : 'toggle_off'}
              </span>
              연결 편집모드
            </button>
          )}
        </Panel>
        <Panel position="top-left" className="!m-3">
          <div className="flex gap-1 rounded-lg border border-[#3c4a42] bg-[#161d19]/90 p-1 text-[10px] font-semibold backdrop-blur">
            <button
              type="button"
              onClick={arrangeRadially}
              disabled={nodes.length === 0}
              className="flex items-center gap-1 rounded-md px-2.5 py-1 text-[#dde4dd] transition-colors hover:bg-[#4edea322] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
              title="Arrange nodes around the selected node"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>radar</span>
              Arrange
            </button>
            <button
              type="button"
              onClick={undoLastLayout}
              disabled={!lastLayoutPositions}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[#86948a] transition-colors hover:bg-[#242c27] hover:text-[#dde4dd] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
              title="Restore positions from before the last radial layout"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>undo</span>
            </button>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  )
}
