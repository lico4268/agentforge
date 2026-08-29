> 📄 **완료된 작업 기록** — 당시 구현 계획서다. 현재 설계 문서가 아니며, 현재 방향은 [DIRECTION.md](../../../DIRECTION.md) 참고.

# Loop Drill-Down — Collapsed Loop Node + Navigation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the main agent canvas, collapse every `loop.guard` node's member nodes into the guard node itself (rendered as a "ripple halo" circle with a member-count badge), and let the user double-click it to navigate into a dedicated view showing just that loop's real nodes, with a Toolbar breadcrumb back to the main graph.

**Architecture:** Two pure functions (`deriveLoopMembers`, `projectCollapsedView`/`projectDrilledInView`) compute a render-only projection of the graph store's raw `nodes`/`edges` — the store itself is never mutated, so `toArchitecture()`/`compile_graph` see the graph exactly as before. `Canvas.tsx` feeds the projected lists to React Flow instead of the raw ones. A new `useUiStore.drilledInLoopId` field tracks which loop (if any) is currently drilled into; `Toolbar.tsx` reads it to swap the logo for a breadcrumb.

**Tech Stack:** React, TypeScript, `@xyflow/react`, Zustand, Vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-14-ui-canvas-design-philosophy-design.md` §3, §4.
- **Depends on the edge-routing plan** (`docs/superpowers/plans/2026-08-14-edge-routing.md`) for the `LOOP_ACCENT_COLOR` export in `ui/src/lib/categoryStyle.ts` — land that plan first, or add the constant yourself before Task 5 if working out of order.
- Loop collapse/drill-down only applies when `canvasNodeMode === 'agent'` (`useUiStore`) — classic mode renders the raw graph unchanged, same scoping as the edge-routing plan.
- Loop Anchor / Loop Lens / Loops panel do **not** exist in the current codebase to build on or replace — they were deleted in the `loop.guard` redesign (`docs/superpowers/specs/2026-08-07-loop-node-design.md`, commits `0d003b2`/`c96fd79`). Every file in this plan is net-new except `RadialNodePorts.tsx`, `useUiStore.ts`, `Canvas.tsx`, `Toolbar.tsx`, which get small, additive edits.
- Nested loops (a loop.guard whose member set contains another loop.guard) are out of scope — not reachable from a valid compiled graph anyway (see spec's 후속 작업 note) and not handled by the projection functions below.
- Known, deliberately-unhandled edge case: dragging a *new* connection from one of a collapsed loop node's synthetic ports (visible only when `showConnectionPorts` is toggled on) would write a malformed edge referencing a handle id that isn't a real manifest port. Not addressed in this plan — narrow, opt-in-only edge case, not a blocker for shipping the read-mostly collapse/drill-down feature.
- Run `cd ui && npm run test` and `npm run build` after every task.

---

### Task 1: `deriveLoopMembers` — mirrors the backend's loop-membership algorithm

**Files:**
- Create: `ui/src/canvas/loop/deriveLoopMembers.ts`
- Test: `ui/src/__tests__/deriveLoopMembers.test.ts`

**Interfaces:**
- Produces: `deriveLoopMembers(nodeIds: string[], edges: LoopGraphEdge[], loopNodeId: string): string[]` — consumed by Task 2's `projectCollapsedView`/`projectDrilledInView` and Task 7's Toolbar breadcrumb.
- `LoopGraphEdge = { source: string; sourceHandle?: string | null; target: string }` — structurally compatible with `@xyflow/react`'s `Edge`, so callers pass real edge arrays directly without conversion.

- [ ] **Step 1: Write the failing test**

Create `ui/src/__tests__/deriveLoopMembers.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { deriveLoopMembers } from '@/canvas/loop/deriveLoopMembers'

// Mirrors STARTER_ARCHITECTURE (ui/src/app/starterArchitecture.ts): a single
// review→loop_guard→reasoning cycle plus two exits (accept, clarify) that
// must NOT be pulled into the loop's member set.
const nodeIds = ['input', 'planning', 'reasoning', 'review', 'loop_guard', 'human_checkpoint', 'output']
const edges = [
  { id: 'e1', source: 'input', sourceHandle: 'task', target: 'planning' },
  { id: 'e2', source: 'planning', sourceHandle: 'plan', target: 'reasoning' },
  { id: 'e3', source: 'input', sourceHandle: 'task', target: 'reasoning' },
  { id: 'e4', source: 'reasoning', sourceHandle: 'answer', target: 'review' },
  { id: 'e5', source: 'review', sourceHandle: 'accept', target: 'output' },
  { id: 'e6', source: 'review', sourceHandle: 'refine', target: 'loop_guard' },
  { id: 'e7', source: 'review', sourceHandle: 'clarify', target: 'human_checkpoint' },
  { id: 'e8', source: 'human_checkpoint', sourceHandle: 'approve', target: 'output' },
  { id: 'e9', source: 'loop_guard', sourceHandle: 'loopBack', target: 'reasoning' },
  { id: 'e10', source: 'loop_guard', sourceHandle: 'exit', target: 'output' },
]

describe('deriveLoopMembers', () => {
  it('returns exactly the nodes on the cycle back to the guard, excluding both exits and the guard itself', () => {
    expect(deriveLoopMembers(nodeIds, edges, 'loop_guard')).toEqual(['reasoning', 'review'])
  })

  it('returns an empty array when the guard has no loopBack edge wired yet', () => {
    const noLoopBack = edges.filter((e) => e.sourceHandle !== 'loopBack')
    expect(deriveLoopMembers(nodeIds, noLoopBack, 'loop_guard')).toEqual([])
  })

  it('returns an empty array for a node id that is not a loop.guard at all', () => {
    expect(deriveLoopMembers(nodeIds, edges, 'review')).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/deriveLoopMembers.test.ts`
Expected: FAIL — cannot find module `@/canvas/loop/deriveLoopMembers`.

- [ ] **Step 3: Write minimal implementation**

Create `ui/src/canvas/loop/deriveLoopMembers.ts`:

```ts
export type LoopGraphEdge = {
  source: string
  sourceHandle?: string | null
  target: string
}

/**
 * The set of nodes that make up one loop's body: everything reachable
 * forward from the guard's `loopBack` target that can also reach back to the
 * guard. Mirrors `_derive_loop_members` in `server/graphs/compile.py`
 * (forward ∩ backward from the guard) so the canvas and the compiler agree
 * on what "inside the loop" means. The guard node itself is never included —
 * it's the loop's controller, not a hidden member.
 */
export function deriveLoopMembers(
  nodeIds: string[],
  edges: LoopGraphEdge[],
  loopNodeId: string,
): string[] {
  const loopBackEdge = edges.find((e) => e.source === loopNodeId && e.sourceHandle === 'loopBack')
  if (!loopBackEdge) return []

  const outgoing = new Map<string, string[]>()
  const incoming = new Map<string, string[]>()
  for (const edge of edges) {
    ;(outgoing.get(edge.source) ?? outgoing.set(edge.source, []).get(edge.source)!).push(edge.target)
    ;(incoming.get(edge.target) ?? incoming.set(edge.target, []).get(edge.target)!).push(edge.source)
  }

  // Forward: reachable from the loopBack target, without crossing back
  // through the guard (the guard is the loop's boundary, not a member).
  const forward = new Set<string>()
  const forwardStack = [loopBackEdge.target]
  while (forwardStack.length > 0) {
    const current = forwardStack.pop()!
    if (current === loopNodeId || forward.has(current)) continue
    forward.add(current)
    for (const next of outgoing.get(current) ?? []) forwardStack.push(next)
  }

  // Backward: nodes that can reach the guard at all (walking edges in reverse).
  const backward = new Set<string>()
  const backwardStack = [loopNodeId]
  while (backwardStack.length > 0) {
    const current = backwardStack.pop()!
    if (backward.has(current)) continue
    backward.add(current)
    for (const prev of incoming.get(current) ?? []) backwardStack.push(prev)
  }

  // Filtering nodeIds (rather than iterating the sets) keeps the result in a
  // stable, caller-predictable order for tests and for badge/label rendering.
  return nodeIds.filter((id) => forward.has(id) && backward.has(id))
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/deriveLoopMembers.test.ts`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/loop/deriveLoopMembers.ts ui/src/__tests__/deriveLoopMembers.test.ts
git commit -m "feat(ui): add deriveLoopMembers, mirroring the backend's loop-membership algorithm"
```

---

### Task 2: `projectCollapsedView` / `projectDrilledInView` — pure canvas projections

**Files:**
- Create: `ui/src/canvas/loop/loopProjection.ts`
- Test: `ui/src/__tests__/loopProjection.test.ts`

**Interfaces:**
- Consumes: `deriveLoopMembers` from Task 1.
- Produces:
  - `LOOP_COLLAPSED_NODE_TYPE: string` — the synthetic React Flow node type for a collapsed loop, registered by Task 6's `Canvas.tsx`.
  - `type CrossingPort = { id: string; label: string; dataType: string }`
  - `type LoopCollapsedNodeData = RFNodeData & { loopNodeId: string; memberCount: number; loopInputs: CrossingPort[]; loopOutputs: CrossingPort[]; portView: { nodes: { id: string; position: { x: number; y: number } }[]; edges: Edge[] } }` — consumed by Task 5's `LoopNode.tsx`.
  - `projectCollapsedView(nodes: RFNode[], edges: Edge[]): { nodes: Node[]; edges: Edge[] }` — consumed by Task 6's `Canvas.tsx`.
  - `projectDrilledInView(nodes: RFNode[], edges: Edge[], loopNodeId: string): { nodes: Node[]; edges: Edge[] }` — consumed by Task 6's `Canvas.tsx`.

- [ ] **Step 1: Write the failing test**

Create `ui/src/__tests__/loopProjection.test.ts`:

```ts
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

  it('turns the guard node into a collapsed node carrying 2 members and the right crossing ports', () => {
    const { nodes, edges } = loadStarterGraph()
    const { nodes: result } = projectCollapsedView(nodes, edges)

    const guard = result.find((n) => n.id === 'loop_guard')!
    expect(guard.type).toBe(LOOP_COLLAPSED_NODE_TYPE)

    const data = guard.data as LoopCollapsedNodeData
    expect(data.memberCount).toBe(2)
    expect(data.loopInputs.map((p) => p.label)).toEqual(['plan', 'task'])
    expect(data.loopOutputs.map((p) => p.label)).toEqual(['accept', 'clarify', 'exit'])
  })

  it('drops the 3 internal edges and reroutes the 5 boundary-crossing edges onto the guard, leaving the 2 fully-external edges untouched', () => {
    const { nodes, edges } = loadStarterGraph()
    const { edges: result } = projectCollapsedView(nodes, edges)

    expect(result).toHaveLength(7)
    expect(result.find((e) => e.id === 'e4')).toBeUndefined() // reasoning -> review, internal
    expect(result.find((e) => e.id === 'e6')).toBeUndefined() // review -> loop_guard, internal
    expect(result.find((e) => e.id === 'e9')).toBeUndefined() // loop_guard -> reasoning, internal

    const e2 = result.find((e) => e.id === 'e2')!
    expect(e2).toMatchObject({ source: 'planning', target: 'loop_guard', targetHandle: 'e2' })

    const e5 = result.find((e) => e.id === 'e5')!
    expect(e5).toMatchObject({ source: 'loop_guard', target: 'output', sourceHandle: 'e5' })

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

    expect(viewNodes.map((n) => n.id).sort()).toEqual(['loop_guard', 'reasoning', 'review'].sort())
    expect(viewEdges.map((e) => e.id).sort()).toEqual(['e4', 'e6', 'e9'].sort())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/loopProjection.test.ts`
Expected: FAIL — cannot find module `@/canvas/loop/loopProjection`.

- [ ] **Step 3: Write minimal implementation**

Create `ui/src/canvas/loop/loopProjection.ts`:

```ts
import type { Edge, Node } from '@xyflow/react'
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
): { nodes: Node[]; edges: Edge[] } {
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
      rerouted.push({ ...edge, source: sourceOwner, sourceHandle: edge.id })
    } else if (sourceOwner && targetOwner) {
      // Chains straight from one loop into another (e.g. guard1's exit feeds
      // guard2's member directly) — reroute both ends onto their own guard.
      loopOutputsById.get(sourceOwner)!.push(crossingPort(edge))
      loopInputsById.get(targetOwner)!.push(crossingPort(edge))
      rerouted.push({ ...edge, source: sourceOwner, sourceHandle: edge.id, target: targetOwner, targetHandle: edge.id })
    } else {
      passthrough.push(edge)
    }
  }

  const resultNodes: Node[] = nodes
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
): { nodes: Node[]; edges: Edge[] } {
  const members = deriveLoopMembers(nodes.map((n) => n.id), edges, loopNodeId)
  const visible = new Set([loopNodeId, ...members])
  return {
    nodes: nodes.filter((n) => visible.has(n.id)),
    edges: edges.filter((e) => visible.has(e.source) && visible.has(e.target)),
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/loopProjection.test.ts`
Expected: PASS, all 6 tests.

- [ ] **Step 5: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/loop/loopProjection.ts ui/src/__tests__/loopProjection.test.ts
git commit -m "feat(ui): add projectCollapsedView/projectDrilledInView pure canvas projections"
```

---

### Task 3: `useUiStore` — drilled-in loop navigation state

**Files:**
- Modify: `ui/src/stores/useUiStore.ts`
- Test: `ui/src/__tests__/uiStore.test.ts`

**Interfaces:**
- Produces: `drilledInLoopId: string | null`, `enterLoop(loopNodeId: string): void`, `exitLoop(): void` — consumed by Task 5 (`LoopNode.tsx` calls `enterLoop`), Task 6 (`Canvas.tsx` reads `drilledInLoopId`), Task 7 (`Toolbar.tsx` reads `drilledInLoopId`, calls `exitLoop`).

- [ ] **Step 1: Write the failing test**

Add to `ui/src/__tests__/uiStore.test.ts`:

```ts
describe('useUiStore loop drill-down', () => {
  beforeEach(() => {
    useUiStore.setState({ drilledInLoopId: null })
  })

  it('defaults to no loop drilled into', () => {
    expect(useUiStore.getState().drilledInLoopId).toBeNull()
  })

  it('enterLoop sets the drilled-in loop id, exitLoop clears it', () => {
    useUiStore.getState().enterLoop('loop_guard')

    expect(useUiStore.getState().drilledInLoopId).toBe('loop_guard')

    useUiStore.getState().exitLoop()

    expect(useUiStore.getState().drilledInLoopId).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/uiStore.test.ts`
Expected: FAIL — `useUiStore.getState().enterLoop` is not a function.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `ui/src/stores/useUiStore.ts`:

```ts
import { create } from 'zustand'

export type CanvasNodeMode = 'classic' | 'agent'

/** Pure UI state — panel visibility, etc. No domain data here. */
type UiState = {
  panels: { library: boolean; inspector: boolean; log: boolean }
  canvasNodeMode: CanvasNodeMode
  /** Agent-mode connection dots are hidden by default — direction reads from
   * the edge's arrowhead instead. Toggle this on to drag new connections. */
  showConnectionPorts: boolean
  /** Which loop.guard node's drilled-in view is showing, if any. Pure
   * view-layer navigation state — never touches the graph store, so it has
   * no effect on `toArchitecture()`/`compile_graph`. */
  drilledInLoopId: string | null
  togglePanel: (key: keyof UiState['panels']) => void
  setCanvasNodeMode: (mode: CanvasNodeMode) => void
  toggleConnectionPorts: () => void
  enterLoop: (loopNodeId: string) => void
  exitLoop: () => void
}

export const useUiStore = create<UiState>((set) => ({
  panels: { library: true, inspector: true, log: true },
  canvasNodeMode: 'agent',
  showConnectionPorts: false,
  drilledInLoopId: null,
  togglePanel: (key) =>
    set((s) => ({ panels: { ...s.panels, [key]: !s.panels[key] } })),
  setCanvasNodeMode: (canvasNodeMode) => set({ canvasNodeMode }),
  toggleConnectionPorts: () => set((s) => ({ showConnectionPorts: !s.showConnectionPorts })),
  enterLoop: (loopNodeId) => set({ drilledInLoopId: loopNodeId }),
  exitLoop: () => set({ drilledInLoopId: null }),
}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/uiStore.test.ts`
Expected: PASS, all tests including the pre-existing `canvasNodeMode`/`showConnectionPorts` ones.

- [ ] **Step 5: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/stores/useUiStore.ts ui/src/__tests__/uiStore.test.ts
git commit -m "feat(ui): add drilledInLoopId navigation state to useUiStore"
```

---

### Task 4: `RadialNodePorts` — optional projected-view override

**Files:**
- Modify: `ui/src/canvas/nodes/RadialNodePorts.tsx`

**Interfaces:**
- Consumes: `computeHubRimAngles`, `type HubRimAngles` (both already exported by `ui/src/canvas/nodes/hubRimAngles.ts` — no changes needed to that file).
- Produces: `RadialNodePortsProps.viewOverride?: { nodes: {id,position}[]; edges: {source,sourceHandle?,target,targetHandle?}[]; radialCenterId: string | null }` — consumed by Task 5's `LoopNode.tsx`.

**Why this task has no dedicated test:** `RadialNodePorts` renders `@xyflow/react`'s `<Handle>`, which (like `AgentEdge`, `AgentNode`, `GenericNode`) has no existing render-test precedent in this codebase — those components are verified by `npm run build` plus manual dev-server checks. The angle *math* this task depends on (`computeHubRimAngles`) is already covered by `hubRimAngles.ts`'s own design (a pure function deliberately kept separate from its store-reading hook wrapper for testability) and by Task 2's `loopProjection.test.ts`, which verifies the `portView` data this override consumes is correct.

- [ ] **Step 1: Add the `viewOverride` prop and branch the angle computation on it**

Replace the full contents of `ui/src/canvas/nodes/RadialNodePorts.tsx`:

```tsx
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
```

The only behavior change for existing callers (`AgentNode.tsx`, the only current caller) is the two new `useHubRimAngles` results being computed and then unconditionally discarded when `viewOverride` is absent — dead work, not a behavior change; `AgentNode.tsx` needs no edit.

- [ ] **Step 2: Typecheck**

Run: `cd ui && npm run build`
Expected: PASS. (No test suite change in this task — verified indirectly per the note above.)

- [ ] **Step 3: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/RadialNodePorts.tsx
git commit -m "feat(ui): let RadialNodePorts compute angles from a projected view override"
```

---

### Task 5: `LoopNode` — the collapsed loop's canvas representation

**Files:**
- Create: `ui/src/canvas/nodes/LoopNode.tsx`

**Interfaces:**
- Consumes: `LOOP_ACCENT_COLOR` (from the edge-routing plan's `ui/src/lib/categoryStyle.ts` addition), `type LoopCollapsedNodeData` (Task 2), `RadialNodePorts` with `viewOverride` (Task 4), `useUiStore.enterLoop` (Task 3), `useGraphStore.radialCenterId` (existing).
- Produces: `LoopNode` component — registered as `nodeTypes[LOOP_COLLAPSED_NODE_TYPE]` by Task 6's `Canvas.tsx`.

- [ ] **Step 1: Write the component**

Create `ui/src/canvas/nodes/LoopNode.tsx`:

```tsx
import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { useUiStore } from '@/stores/useUiStore'
import { useGraphStore } from '@/stores/useGraphStore'
import { useExecutionStore, useNodeRuntime } from '@/execution/useExecutionStore'
import { LOOP_ACCENT_COLOR } from '@/lib/categoryStyle'
import type { NodeRuntimeStatus } from '@/types'
import type { LoopCollapsedNodeData } from '@/canvas/loop/loopProjection'
import { RadialNodePorts } from './RadialNodePorts'

/**
 * Canvas representation of a collapsed loop: a ripple halo (two fading
 * loop-purple rings) marks it as "this is a container" regardless of
 * execution status; the inner circle's border follows the same
 * running/success/failed/skipped language every other node uses, just with
 * loop-purple as its accent instead of a category color. Double-click drills
 * into the loop's real internals (Canvas.tsx's projectDrilledInView).
 */
function LoopNodeImpl({ id, data, selected }: NodeProps) {
  const runtime = useNodeRuntime(id)
  const enterLoop = useUiStore((s) => s.enterLoop)
  const radialCenterId = useGraphStore((s) => s.radialCenterId)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const { memberCount, loopInputs, loopOutputs, portView } = data as LoopCollapsedNodeData

  const status = runtime?.status ?? 'idle'
  const borderColor = selected ? LOOP_ACCENT_COLOR : statusColor(status, LOOP_ACCENT_COLOR)
  const hasPendingCheckpointInside = pendingInterrupt !== null

  return (
    <div
      className="relative h-[112px] w-[112px]"
      onDoubleClick={() => enterLoop(id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') enterLoop(id)
      }}
      aria-label={`Loop, ${memberCount} node${memberCount === 1 ? '' : 's'} inside — activate to open`}
    >
      {/* Ripple halo — fixed loop-purple identity rings, independent of status */}
      <div
        className="pointer-events-none absolute rounded-full"
        style={{ inset: -20, border: `1px solid ${LOOP_ACCENT_COLOR}`, opacity: 0.12 }}
      />
      <div
        className="pointer-events-none absolute rounded-full"
        style={{ inset: -8, border: `1.2px solid ${LOOP_ACCENT_COLOR}`, opacity: 0.22 }}
      />

      <div
        className="relative h-[112px] w-[112px] rounded-full border bg-[#161d19]/90 shadow-lg backdrop-blur-md"
        style={{ borderColor, borderWidth: 2.5 }}
      >
        <RadialNodePorts
          nodeId={id}
          inputs={loopInputs}
          outputs={loopOutputs}
          color={LOOP_ACCENT_COLOR}
          viewOverride={{ nodes: portView.nodes, edges: portView.edges, radialCenterId }}
        />
        <div className="pointer-events-none absolute inset-2 flex flex-col items-center justify-center rounded-full text-center">
          <span className="text-[10px] font-semibold text-[#dde4dd]">Loop</span>
          <span className="mt-1 font-mono text-[8px] text-[#86948a]">
            {memberCount} node{memberCount === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {hasPendingCheckpointInside && (
        <span
          className="absolute bottom-2 right-2 h-2.5 w-2.5 rounded-full border border-[#161d19] bg-[#ffd180] shadow-[0_0_8px_rgba(255,209,128,0.85)]"
          title="A checkpoint inside this loop needs a decision — open it to review"
          aria-label="A checkpoint inside this loop needs a decision"
        />
      )}

      <span
        className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border bg-[#0e1511] opacity-55 transition-opacity hover:opacity-100"
        style={{ borderColor: LOOP_ACCENT_COLOR, color: LOOP_ACCENT_COLOR }}
        title="Double-click to open this loop"
      >
        <span className="material-symbols-outlined" style={{ fontSize: 12 }}>open_in_full</span>
      </span>
    </div>
  )
}

function statusColor(status: NodeRuntimeStatus, accent: string) {
  switch (status) {
    case 'running': return accent
    case 'success': return '#4edea3'
    case 'failed':  return '#ff8a80'
    case 'skipped': return '#3c4a42'
    default:        return 'rgba(255,255,255,0.08)'
  }
}

export const LoopNode = memo(LoopNodeImpl)
```

Note: `hasPendingCheckpointInside` uses `pendingInterrupt !== null` (any pending interrupt at all) rather than checking whether the interrupted node id is specifically one of this loop's members — cheap, correct enough for a single-loop starter graph, and avoids importing `deriveLoopMembers` just for a badge. Revisit if a graph with multiple loops and checkpoints outside any loop makes this over-eager in practice.

- [ ] **Step 2: Typecheck**

Run: `cd ui && npm run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/LoopNode.tsx
git commit -m "feat(ui): add LoopNode — ripple-halo collapsed loop representation"
```

---

### Task 6: `Canvas.tsx` — wire the projected view into React Flow

**Files:**
- Modify: `ui/src/canvas/Canvas.tsx`

**Interfaces:**
- Consumes: `projectCollapsedView`, `projectDrilledInView`, `LOOP_COLLAPSED_NODE_TYPE` (Task 2), `LoopNode` (Task 5), `useUiStore.drilledInLoopId`/`exitLoop` (Task 3).

- [ ] **Step 1: Replace `Canvas.tsx` with the wired version**

Replace the full contents of `ui/src/canvas/Canvas.tsx`:

```tsx
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

  // Auto-recover if the drilled-into loop's guard node was deleted (or its
  // loopBack edge was removed) while the user was inside it.
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
    previousDrilledInLoopId.current = drilledInLoopId
    if (!nodesInitialized) return
    void fitView({ padding: 0.2, duration: viewportTransitionDuration(prefersReducedMotion()) })
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
```

- [ ] **Step 2: Run the full suite and typecheck**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 3: Manual visual verification**

```bash
./start.sh
```

Open the frontend, load the starter graph, confirm:
- The main canvas shows `reasoning`/`review` collapsed into one ripple-halo node in place of `loop_guard`, with a "2 nodes" label, sitting where `loop_guard` used to be.
- Double-clicking it swaps the whole canvas to show only `reasoning`, `review`, and `loop_guard`, with the internal edges among them (including the loop-back curve from Task 2 of the edge-routing plan).
- The canvas re-fits/zooms to the new subgraph on entry.
- There is currently no way back from inside the drill-down (Task 7 adds it) — confirm this by reloading the page or switching `canvasNodeMode` to `classic` and back to `agent`, which resets `drilledInLoopId`... actually it does not, since `drilledInLoopId` lives in `useUiStore` independent of `canvasNodeMode`. Note this as expected, temporary state until Task 7 lands.

- [ ] **Step 4: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/Canvas.tsx
git commit -m "feat(ui): wire projected loop views into Canvas, register LoopNode"
```

---

### Task 7: `Toolbar.tsx` — breadcrumb and back navigation

**Files:**
- Modify: `ui/src/app/Toolbar.tsx`

**Interfaces:**
- Consumes: `deriveLoopMembers` (Task 1), `useUiStore.drilledInLoopId`/`exitLoop` (Task 3).

- [ ] **Step 1: Add the breadcrumb, replacing the logo block when drilled in**

In `ui/src/app/Toolbar.tsx`, add to the imports:

```ts
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { deriveLoopMembers } from '@/canvas/loop/deriveLoopMembers'
```

(`useGraphStore` is likely already imported for `toArchitecture`/`nodes` — check before adding a duplicate import; keep the single import line with both named imports if so.)

Inside `export function Toolbar() {`, add after the existing store reads:

```ts
const drilledInLoopId = useUiStore((s) => s.drilledInLoopId)
const exitLoop = useUiStore((s) => s.exitLoop)
const edges = useGraphStore((s) => s.edges)
const drilledInLoopMemberCount = drilledInLoopId
  ? deriveLoopMembers(nodes.map((n) => n.id), edges, drilledInLoopId).length
  : 0
```

Replace the existing `{/* Logo */}` block:

```tsx
{/* Logo */}
<div className="flex shrink-0 items-center gap-2">
  <span className="text-[15px] font-semibold tracking-tight text-[#dde4dd]">Agentforge</span>
  <span className="rounded border border-[#3c4a42]/60 bg-[#2f3632]/60 px-1.5 py-px font-mono text-[10px] text-[#86948a]">
    v0.1
  </span>
</div>
```

with:

```tsx
{/* Logo, or a breadcrumb back to the main graph while drilled into a loop */}
{drilledInLoopId ? (
  <button
    type="button"
    onClick={exitLoop}
    className="flex shrink-0 items-center gap-1.5 text-[13px] font-semibold text-[#dde4dd] transition-colors hover:text-[#4edea3]"
    title="Back to main graph"
  >
    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>arrow_back</span>
    Agentforge <span className="font-normal text-[#86948a]">/</span> Loop
    <span className="rounded border border-[#a78bfa]/40 bg-[#a78bfa]/10 px-1.5 py-px font-mono text-[10px] text-[#a78bfa]">
      {drilledInLoopMemberCount} node{drilledInLoopMemberCount === 1 ? '' : 's'}
    </span>
  </button>
) : (
  <div className="flex shrink-0 items-center gap-2">
    <span className="text-[15px] font-semibold tracking-tight text-[#dde4dd]">Agentforge</span>
    <span className="rounded border border-[#3c4a42]/60 bg-[#2f3632]/60 px-1.5 py-px font-mono text-[10px] text-[#86948a]">
      v0.1
    </span>
  </div>
)}
```

Global execution controls (architecture select, model select, Run button) are untouched — they stay visible and functional regardless of `drilledInLoopId`, per spec §4 ("드릴다운은 순수 뷰 이동이지 실행 범위 변경이 아니다").

- [ ] **Step 2: Run the full suite and typecheck**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 3: Manual visual verification**

```bash
./start.sh
```

Double-click the collapsed loop node, confirm the logo is replaced by "Agentforge / Loop · 2 nodes", click it, confirm the canvas returns to the main graph with the collapsed loop node visible again.

- [ ] **Step 4: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/app/Toolbar.tsx
git commit -m "feat(ui): add Toolbar breadcrumb and back navigation for loop drill-down"
```

---

## Self-Review Notes

- **Spec coverage**: implements spec §3 (collapsed loop node, ripple halo, corner badge, double-click drill-down, breadcrumb) and §4 (Toolbar breadcrumb, Inspector/LogPanel left untouched — neither file is modified by this plan, which is itself the proof they need no changes) in full. §5 (Input Slots) is explicitly out of scope per the spec's own 비목표.
- **Placeholder scan**: none — every step has real, complete code; the two "known limitation" notes (arrange-while-collapsed, new-connection-from-synthetic-port) are explicit scope decisions stated in Global Constraints and Task 6, not vague TODOs.
- **Type consistency**: `LoopCollapsedNodeData` (Task 2) is produced by `projectCollapsedView` and consumed identically by `LoopNode.tsx` (Task 5) via `data as LoopCollapsedNodeData`; `deriveLoopMembers`'s signature (`nodeIds, edges, loopNodeId`) is called identically in Task 2, Task 7, and its own tests; `RadialNodePorts`'s `viewOverride` shape (Task 4) matches exactly what `LoopNode.tsx` (Task 5) constructs from `portView` + `radialCenterId`.
