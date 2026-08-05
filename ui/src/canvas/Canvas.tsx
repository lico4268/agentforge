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
  type Edge,
} from '@xyflow/react'
import { useShallow } from 'zustand/react/shallow'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore, type CanvasNodeMode } from '@/stores/useUiStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { GenericNode } from './nodes/GenericNode'
import { AgentNode } from './nodes/AgentNode'
import { LoopScopeNode, LOOP_SCOPE_DIAMETER, type LoopScopeNodeData } from './nodes/LoopScopeNode'
import { AgentEdge } from './edges/AgentEdge'
import { radialLayout } from './layout/radialLayout'
import { prefersReducedMotion, viewportTransitionDuration } from './viewport'
import { DRAG_MIME } from './dragTypes'
import { buildLoopScopes, type LoopScope } from './loops/loopScopes'
import { projectLoopScopes } from './loops/loopScopeProjection'
import { computeBoundaryPortAngles } from './loops/loopScopeBoundaryPorts'
import { findTier3FeedbackEdgeIds } from './loops/loopEdgeAnnotations'
import { computeTier3LoopLane } from './loops/tier3LoopLane'
import type { RFNode, RFNodeData } from '@/stores/useGraphStore'

const NODE_DIAMETER = 112

type LoopScopeRFNode = { id: string; type: 'loopScope'; position: { x: number; y: number }; draggable: false; data: LoopScopeNodeData }

/** Real-node center points (position is top-left in React Flow) — used to
 * aim a collapsed container's boundary ports at their actual partners. */
function centerPointsById(nodes: RFNode[]): Map<string, { x: number; y: number }> {
  return new Map(
    nodes.map((n) => [n.id, { x: n.position.x + NODE_DIAMETER / 2, y: n.position.y + NODE_DIAMETER / 2 }]),
  )
}

function useProjectedCanvas(nodes: RFNode[], edges: Edge[], canvasNodeMode: CanvasNodeMode) {
  const expandedLoopScopeIds = useUiStore((s) => s.expandedLoopScopeIds)
  const rawExecutionView = useUiStore((s) => s.rawExecutionView)

  return useMemo(() => {
    if (canvasNodeMode !== 'agent' || rawExecutionView) return { nodes, edges }

    const loopScopes = buildLoopScopes(
      nodes.map((n) => n.id),
      edges,
    )
    if (loopScopes.length === 0) return { nodes, edges }

    const partnerCenters = centerPointsById(nodes)
    const createContainerNode = (scope: LoopScope, position: { x: number; y: number }, memberNodes: RFNode[]): LoopScopeRFNode => {
      const containerCenter = { x: position.x + LOOP_SCOPE_DIAMETER / 2, y: position.y + LOOP_SCOPE_DIAMETER / 2 }
      return {
        id: scope.id,
        type: 'loopScope',
        position,
        draggable: false,
        data: {
          manifestType: 'loopScope',
          config: {},
          loopScopeId: scope.id,
          tier: scope.tier,
          memberNodeIds: scope.memberNodeIds,
          memberNodes,
          boundaryPorts: computeBoundaryPortAngles(containerCenter, scope, edges, partnerCenters),
        },
      }
    }

    const result = projectLoopScopes(nodes, edges, loopScopes, expandedLoopScopeIds, createContainerNode)
    const finalNodes = result.nodes.map((n) => {
      if (n.type === 'loopScope') return n
      const isReentry = result.reentryNodeIds.has(n.id)
      const collapseAffordance = Object.entries(result.collapseAffordanceNodeIdByScopeId).find(
        ([, memberId]) => memberId === n.id,
      )?.[0]
      if (!isReentry && !collapseAffordance) return n
      return {
        ...n,
        data: { ...(n.data as RFNodeData), loopReentry: isReentry, loopScopeCollapseAffordance: collapseAffordance },
      }
    })

    return { nodes: finalNodes, edges: result.edges }
  }, [nodes, edges, canvasNodeMode, expandedLoopScopeIds, rawExecutionView])
}

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
  const rawExecutionView = useUiStore((s) => s.rawExecutionView)
  const toggleRawExecutionView = useUiStore((s) => s.toggleRawExecutionView)

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
    radialCenterId,
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
        radialCenterId: s.radialCenterId,
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

  const nodeTypes: NodeTypes = useMemo(() => {
    const map: NodeTypes = { loopScope: LoopScopeNode }
    for (const m of registry.all()) {
      map[m.type] = registry.customComponent(m.type) ?? (canvasNodeMode === 'agent' ? AgentNode : GenericNode)
    }
    return map
  }, [canvasNodeMode, registry])
  const edgeTypes: EdgeTypes = useMemo(() => ({ agent: AgentEdge }), [])
  const projected = useProjectedCanvas(nodes, edges, canvasNodeMode)
  const tier3FeedbackEdgeIds = useMemo(
    () => findTier3FeedbackEdgeIds(nodes.map((node) => node.id), edges),
    [nodes, edges],
  )
  const tier3LoopLane = useMemo(
    () => computeTier3LoopLane(nodes, radialCenterId),
    [nodes, radialCenterId],
  )
  const tier3LaneOffsetByEdgeId = useMemo(
    () => new Map(
      edges
        .filter((edge) => tier3FeedbackEdgeIds.has(edge.id))
        .map((edge, index) => [edge.id, index * 14]),
    ),
    [edges, tier3FeedbackEdgeIds],
  )
  const renderedEdges = useMemo(
    () =>
      canvasNodeMode === 'agent'
        ? projected.edges.map((edge) => ({
            ...edge,
            type: 'agent',
            data: {
              ...edge.data,
              loopFeedback: tier3FeedbackEdgeIds.has(edge.id),
              loopLane: tier3FeedbackEdgeIds.has(edge.id) && tier3LoopLane
                ? { ...tier3LoopLane, offset: tier3LaneOffsetByEdgeId.get(edge.id) ?? 0 }
                : undefined,
            },
          }))
        : projected.edges,
    [canvasNodeMode, projected.edges, tier3FeedbackEdgeIds, tier3LaneOffsetByEdgeId, tier3LoopLane],
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
        nodes={projected.nodes}
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
            if (n.type === 'loopScope') return '#4edea3'
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
          {canvasNodeMode === 'agent' && (
            <button
              type="button"
              onClick={toggleRawExecutionView}
              aria-pressed={rawExecutionView}
              title="Bypass every Loop Scope container and show the real nodes/edges LangGraph actually executes"
              className="flex items-center gap-1 rounded-lg border border-[#3c4a42] bg-[#161d19]/90 px-2.5 py-1 text-[10px] font-semibold backdrop-blur transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
              style={{ color: rawExecutionView ? '#4edea3' : '#86948a' }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                {rawExecutionView ? 'toggle_on' : 'toggle_off'}
              </span>
              Show execution edges
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
