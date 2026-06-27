import { useCallback, useEffect, useMemo, useRef, type DragEvent } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useReactFlow,
  type NodeTypes,
} from '@xyflow/react'
import { useShallow } from 'zustand/react/shallow'
import { useGraphStore } from '@/stores/useGraphStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { GenericNode } from './nodes/GenericNode'
import { DRAG_MIME } from './dragTypes'

/**
 * The canvas. `nodeTypes` is built from the registry — every manifest type maps
 * to its custom component or GenericNode — so the editor never hardcodes node
 * components. See ui-architecture.md §5.
 */
export function Canvas() {
  const registry = useRegistry()
  const { screenToFlowPosition, fitView } = useReactFlow()
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Re-fit whenever the canvas container resizes. The resizable panels settle
  // their dimensions after mount, so a single mount-time fitView lands wrong.
  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const observer = new ResizeObserver(() => {
      void fitView({ padding: 0.2 })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [fitView])

  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, select } =
    useGraphStore(
      useShallow((s) => ({
        nodes: s.nodes,
        edges: s.edges,
        onNodesChange: s.onNodesChange,
        onEdgesChange: s.onEdgesChange,
        onConnect: s.onConnect,
        addNode: s.addNode,
        select: s.select,
      })),
    )

  const nodeTypes: NodeTypes = useMemo(() => {
    const map: NodeTypes = {}
    for (const m of registry.all()) {
      map[m.type] = registry.customComponent(m.type) ?? GenericNode
    }
    return map
  }, [registry])

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

  return (
    <div ref={wrapperRef} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={(_, node) => select(node.id)}
        onPaneClick={() => select(null)}
        colorMode="dark"
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1c2333" />
        <Controls className="!bg-[#11151f] !border-white/10" />
        <MiniMap
          pannable
          zoomable
          className="!bg-[#11151f]"
          nodeColor={(n) => {
            const m = registry.get((n.data as { manifestType: string }).manifestType)
            return m ? CATEGORY_META[m.category].color : '#475569'
          }}
        />
      </ReactFlow>
    </div>
  )
}
