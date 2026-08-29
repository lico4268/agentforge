> 📄 **완료된 작업 기록** — 당시 구현 계획서다. 현재 설계 문서가 아니며, 현재 방향은 [DIRECTION.md](../../../DIRECTION.md) 참고.

# Loop Reentry Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synthetic, view-only "loop boundary marker" nodes in the drilled-in loop view with one new real, first-class node type (`loop.reentry` / "Loop Start") that users can drag from the node library, position, and wire like any other node.

**Architecture:** Backend already has a zero-config "passthrough" node mechanism (`PASSTHROUGH_TYPES` in `server/graphs/compile.py`) used by `io.input`/`io.output`/`model.binding` — adding `loop.reentry` to that set is the entire backend implementation. On the frontend, the manifest-driven rendering pipeline (`GenericNode`/`AgentNode` + the node registry) already renders any manifest with no custom component, so `loop.reentry` needs no new React component either — it renders exactly like `review.intent` or `loop.guard` do today. `loop.guard` itself is unchanged; it already is a real node and already represents the loop's "end" — only the "start" side was synthetic, so only the start side gets a real node type.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph (backend), React + TypeScript / Vite / Zustand / `@xyflow/react` (frontend), pytest (backend tests), vitest (frontend tests).

**Spec:** `docs/superpowers/specs/2026-08-22-loop-reentry-node-design.md`

## Global Constraints

- Adding the new node type must cost exactly one `PASSTHROUGH_TYPES` entry on the backend — no new node factory function (per spec §2, `_make_passthrough_node`'s existing fallback branch already returns `output=None, updates={}` for any non-`io.*` passthrough type).
- `loop.guard` is unchanged — no rename, no config migration, no new ports (per spec goals).
- Placing a `loop.reentry` node is optional — `loop.guard`'s `loopBack` may still target a body node directly with no `loop.reentry` in between, exactly as today (per spec goals).
- The synthetic marker system added this session (`LoopBoundaryNode.tsx` and its wiring) is deleted in full, not deprecated or left dead (per spec §3).
- `projectDrilledInView` stops hiding the `loopBack` edge — once `loop.reentry` is a real node, that edge is real and renders like any other edge (per spec §3, amended).
- Final verification on every task: `npm run test -- --run` and `npm run build` (frontend, repo convention — passing tests does not guarantee `tsc -b` passes) plus `pytest` (backend) must all be green before moving to the next task.
- **Discovered during Task 1's review (ruling, see workspace ledger):** `_build_plain_edge_plan` (`server/graphs/compile.py:551`) already requires an explicit `joinMode` on any node with 2+ plain (non-conditional-routing) incoming edges — except when at least one of those edges' source is a conditional-routing type (`review.intent`/`human.checkpoint`/`loop.guard`, `_CONDITIONAL_ROUTING_TYPES` at line 548), in which case no `joinMode` is required at all. The starter graph's `reasoning` node relies on exactly this today (its incoming is `planning`, `input`, and `guard`'s `loopBack` — the `guard` edge is what exempts it). Once Task 4 reroutes the guard's `loopBack` through `loop.reentry`, `reasoning`'s incoming becomes `planning`, `input`, `loop_reentry` — **no conditional-routing source touches it anymore**, so it would newly require a `joinMode`. There is no frontend authoring path for `joinMode` yet (no field on `GraphNodeSchema`, no Inspector UI, and `useGraphStore`'s `loadArchitecture`/`toArchitecture` don't round-trip it) — adding one is out of scope for this plan. The fix belongs in `_build_plain_edge_plan` itself: extend the *existing* exemption to also cover edges sourced from `loop.reentry` specifically (not the whole `PASSTHROUGH_TYPES` set — `io.input`/`io.output`/`model.binding` must keep requiring an explicit `joinMode` when they genuinely fan into a shared target, since unlike `loop.reentry` they are not downstream of a Command-based routing jump). Task 1 includes this fix; Task 4 depends on it and needs no `joinMode` additions of its own as a result.

---

### Task 1: Backend — `loop.reentry` node type

**Files:**
- Modify: `server/manifests.py:211` (insert after the `loop.guard` block, before `human.checkpoint`)
- Modify: `server/graphs/compile.py:52` (`PASSTHROUGH_TYPES`)
- Test: `server/tests/test_compile.py` (new test, append near the other loop tests)
- Test: `server/tests/test_manifests.py` (new test, append after `test_loop_guard_manifest_exposes_all_five_guard_axes`)

**Interfaces:**
- Produces: manifest `type: "loop.reentry"` with `runtime: "passthrough"`, `category: "policy"`, one input port `in` (dataType `any`, required), one output port `out` (dataType `any`), no config fields. Later tasks (2, 4) depend on this exact shape.

- [ ] **Step 1: Write the failing backend test**

Add to `server/tests/test_compile.py`, after `test_review_refine_loop_then_accept` (around line 341):

```python
async def test_loop_reentry_node_passes_through_without_touching_state(monkeypatch):
    """loop.reentry는 loopBack 경로에 끼어도 순수 통과 노드라, 실행 결과가
    reentry 노드가 없을 때(test_review_refine_loop_then_accept)와 동일해야 한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    calls = {"review": 0}

    async def fake_review_llm_step(state, *, node_id, **kwargs):
        calls["review"] += 1
        if calls["review"] == 1:
            return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])
        return _delta([{"id": "c1", "verdict": "met", "evidence": "ok"}])

    monkeypatch.setattr(review_mod, "run_llm_step", fake_review_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", {}),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("reentry", "loop.reentry"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reentry", "loopBack", "in"),
            _edge("reentry", "reasoning", "out", "task"),
            _edge("guard", "output", "exit", "result"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-reentry"}},
    )

    assert final["review_branch"] == "accept"
    assert final["retries"] == 1

    reentry_events = [e for e in emitter.events if e.node_id == "reentry"]
    assert [e.event_type for e in reentry_events] == ["node_start", "node_end"]
    assert reentry_events[-1].output is None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd server && ../server/.venv/bin/pytest tests/test_compile.py -k test_loop_reentry_node_passes_through -v`
Expected: FAIL with `ValueError: Unknown node type: 'loop.reentry' (node 'reentry')`

- [ ] **Step 3: Add the manifest entry**

In `server/manifests.py`, insert right after the `loop.guard` block's closing `},` (currently line 211) and before the `human.checkpoint` block:

```python
    {
        "type": "loop.reentry",
        "runtime": "passthrough",
        "category": "policy",
        "label": "Loop Start",
        "description": "루프가 다시 도는 지점을 표시하는 시각 마커. 로직 없이 입력을 그대로 통과시킨다 — loop.guard의 loopBack 포트를 여기로 연결.",
        "inputs": [{"id": "in", "label": "In", "dataType": "any", "required": True}],
        "outputs": [{"id": "out", "label": "Out", "dataType": "any"}],
        "config": [],
    },
```

- [ ] **Step 4: Add the type to `PASSTHROUGH_TYPES`**

In `server/graphs/compile.py`, change line 52:

```python
PASSTHROUGH_TYPES = {"io.input", "io.output", "model.binding", "loop.reentry"}
```

- [ ] **Step 4b: Extend `_build_plain_edge_plan`'s existing join-mode exemption to `loop.reentry`**

See Global Constraints for why this is needed (a `loop.reentry` node sitting between `loop.guard` and a loop-body node removes the conditional-routing source that today exempts that target from needing a `joinMode`). In `server/graphs/compile.py`, inside `_build_plain_edge_plan` (around line 574-579), change:

```python
        source_type = nodes_by_id.get(e["source"], {}).get("type")
        if source_type in _CONDITIONAL_ROUTING_TYPES:
            has_conditional_source[target] = True
            continue
        sources = plain_sources_by_target.setdefault(target, [])
```

to:

```python
        source_type = nodes_by_id.get(e["source"], {}).get("type")
        if source_type in _CONDITIONAL_ROUTING_TYPES:
            has_conditional_source[target] = True
            continue
        if source_type == "loop.reentry":
            has_conditional_source[target] = True
        sources = plain_sources_by_target.setdefault(target, [])
```

(Do **not** use `continue` for the `loop.reentry` branch — unlike `_CONDITIONAL_ROUTING_TYPES` sources, `loop.reentry`'s edge is a genuine plain edge that still needs a real `graph.add_edge` call; it only needs to be *exempt from requiring `joinMode`*, not excluded from the plan entirely.)

Update the docstring's third paragraph (currently starting "Passthrough 타입도 마찬가지다") to:

```
    loop.reentry도 마찬가지다 — loop.guard의 loopBack이 도착하는 노드일 뿐, 그
    자신도 Command(goto=...) 점프의 하류에서만 실행되므로 다중 소스 타겟의 경우
    joinMode를 요구하지 않는다. 다른 passthrough 타입(io.input/io.output/
    model.binding)은 이 예외에 포함되지 않는다 — 이들은 정적으로 항상 실행되므로
    실제로 여러 소스가 한 target에 모이면 명시적 joinMode 결정이 여전히 필요하다.
```

- [ ] **Step 4c: Run the existing `_build_plain_edge_plan` test suite to confirm no regressions**

Run: `cd server && ../server/.venv/bin/pytest tests/test_compile.py -k "plain_edge_plan" -v`
Expected: all pass, including `test_build_plain_edge_plan_forces_or_when_a_conditional_source_is_mixed_in` and the two-plain-plus-conditional test — these must keep passing unchanged, since this fix only adds a new narrow case, it doesn't touch the `_CONDITIONAL_ROUTING_TYPES` path at all.

- [ ] **Step 4d: Add a direct unit test for the new exemption**

Add to `server/tests/test_compile.py`, near `test_build_plain_edge_plan_forces_or_when_a_conditional_source_is_mixed_in` (around line 1063):

```python
def test_build_plain_edge_plan_forces_or_when_a_loop_reentry_source_is_mixed_in():
    """loop.reentry는 conditional-routing 타입이 아니라 진짜 plain 소스지만,
    loop.guard의 Command(goto=...) 점프 하류에서만 실행되므로 다른 passthrough
    타입과 달리 joinMode 없이도 에러 없이 개별 엣지로 처리돼야 한다."""
    nodes = [
        _node("input", "io.input"),
        _node("reentry", "loop.reentry"),
        _node("reasoning", "reasoning.cot"),  # joinMode 미선언이어도 에러 없어야 함
    ]
    edges = [
        _edge("input", "reasoning", "task"),
        _edge("reentry", "reasoning", "out", "task"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert sorted(plan) == [(["input"], "reasoning"), (["reentry"], "reasoning")]


def test_build_plain_edge_plan_still_requires_join_mode_for_two_plain_passthrough_sources():
    """loop.reentry가 아닌 다른 passthrough 타입(io.input/io.output/model.binding)은
    이번 예외에 포함되지 않는다 — 실제로 2개 이상 모이면 여전히 joinMode가 필요하다."""
    nodes = [
        _node("a", "io.input"),
        _node("b", "model.binding"),
        _node("target", "io.output"),  # joinMode 미선언 — 에러가 나야 함
    ]
    edges = [_edge("a", "target"), _edge("b", "target")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)
```

Run: `cd server && ../server/.venv/bin/pytest tests/test_compile.py -k "loop_reentry_source_is_mixed_in or still_requires_join_mode" -v`
Expected: both PASS.

- [ ] **Step 5: Run the test again to confirm it passes**

Run: `cd server && ../server/.venv/bin/pytest tests/test_compile.py -k test_loop_reentry_node_passes_through -v`
Expected: PASS

- [ ] **Step 6: Add the manifest-declaration test**

Add to `server/tests/test_manifests.py`, after `test_loop_guard_manifest_exposes_all_five_guard_axes`:

```python
def test_loop_reentry_manifest_declares_one_passthrough_in_and_out(client):
    manifests = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert "loop.reentry" in manifests, "loop.reentry 매니페스트가 /api/nodes에 없다"

    reentry = manifests["loop.reentry"]
    assert reentry["runtime"] == "passthrough"
    assert reentry["category"] == "policy"
    assert [(p["id"], p["label"]) for p in reentry["inputs"]] == [("in", "In")]
    assert [(p["id"], p["label"]) for p in reentry["outputs"]] == [("out", "Out")]
    assert reentry["config"] == []
```

- [ ] **Step 7: Run the full backend test suite**

Run: `cd server && ../server/.venv/bin/pytest -q`
Expected: all tests pass (no regressions in `test_compile.py`/`test_manifests.py` or elsewhere)

- [ ] **Step 8: Commit**

```bash
git add server/manifests.py server/graphs/compile.py server/tests/test_compile.py server/tests/test_manifests.py
git commit -m "feat(server): add loop.reentry passthrough node type"
```

---

### Task 2: Frontend registry — mirror the manifest

**Files:**
- Modify: `ui/src/types/manifest.ts:55` (`RUNTIMES` tuple)
- Modify: `ui/src/registry/builtinManifests.ts` (insert after the `loop.guard` entry, in the `// ── Policy / Loop ──` section)
- Modify: `ui/src/lib/categoryStyle.ts` (`NODE_TYPE_ICONS`)
- Test: `ui/src/__tests__/loopReentryManifest.test.tsx` (new file, mirrors `loopGuardManifest.test.tsx`)

**Interfaces:**
- Consumes: the exact manifest shape produced by Task 1 (`type: 'loop.reentry'`, `runtime: 'passthrough'`, `category: 'policy'`, ports `in`/`out`, empty `config`) — this task's bundled fallback copy must match it field-for-field.
- Produces: `'loop.reentry'` becomes a resolvable type in `NodeRegistry`/`BUILTIN_MANIFESTS` — Task 4's starter graph depends on this.

- [ ] **Step 1: Write the failing frontend test**

Create `ui/src/__tests__/loopReentryManifest.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { GenericNode } from '@/canvas/nodes/GenericNode'
import { NodeManifestListSchema } from '@/types'

const loopReentry = BUILTIN_MANIFESTS.find((m) => m.type === 'loop.reentry')!

describe('loop.reentry 매니페스트', () => {
  it('In 입력 1개와 Out 출력 1개를 선언한다', () => {
    expect(loopReentry).toBeDefined()
    expect(loopReentry.inputs.map((p) => [p.id, p.label])).toEqual([['in', 'In']])
    expect(loopReentry.outputs.map((p) => [p.id, p.label])).toEqual([['out', 'Out']])
    expect(loopReentry.config).toEqual([])
  })

  it("runtime 'passthrough'가 NodeManifestSchema를 통과한다", () => {
    expect(() => NodeManifestListSchema.parse(BUILTIN_MANIFESTS)).not.toThrow()
    expect(loopReentry.runtime).toBe('passthrough')
    expect(loopReentry.category).toBe('policy')
  })
})

describe('loop.reentry 렌더링', () => {
  it('커스텀 렌더러 없이 GenericNode가 In/Out 포트를 그린다', () => {
    const registry = new NodeRegistry(BUILTIN_MANIFESTS)
    expect(registry.customComponent('loop.reentry')).toBeUndefined()

    const props = {
      id: 'reentry-1',
      type: 'loop.reentry',
      data: { manifestType: 'loop.reentry', config: {} },
      selected: false,
      dragging: false,
      zIndex: 0,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
    } as unknown as NodeProps

    render(
      <ReactFlowProvider>
        <RegistryProvider value={registry}>
          <GenericNode {...props} />
        </RegistryProvider>
      </ReactFlowProvider>,
    )

    expect(screen.getByText('Loop Start')).toBeInTheDocument()
    expect(screen.getByText('In')).toBeInTheDocument()
    expect(screen.getByText('Out')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npm run test -- --run loopReentryManifest`
Expected: FAIL — `loopReentry` is `undefined` (not in `BUILTIN_MANIFESTS` yet), first assertion throws on `.inputs` of `undefined`.

- [ ] **Step 3: Add `'passthrough'` to `RUNTIMES`**

In `ui/src/types/manifest.ts:55`:

```ts
const RUNTIMES = ['llm_step', 'policy', 'review', 'checkpoint', 'model', 'io', 'loop_guard', 'passthrough'] as const
```

- [ ] **Step 4: Mirror the manifest in the bundled fallback**

In `ui/src/registry/builtinManifests.ts`, insert right after the `loop.guard` entry closes (currently line 254's `},`) and before the `// ── Human ──` comment (currently line 256):

```ts

  {
    type: 'loop.reentry',
    runtime: 'passthrough',
    category: 'policy',
    label: 'Loop Start',
    description: '루프가 다시 도는 지점을 표시하는 시각 마커. 로직 없이 입력을 그대로 통과시킨다 — loop.guard의 loopBack 포트를 여기로 연결.',
    inputs: [{ id: 'in', label: 'In', dataType: 'any', required: true }],
    outputs: [{ id: 'out', label: 'Out', dataType: 'any' }],
    config: [],
  },
```

- [ ] **Step 5: Add the node-library icon**

In `ui/src/lib/categoryStyle.ts`, add to `NODE_TYPE_ICONS` (after the `'io.output': 'logout',` line):

```ts
  'loop.reentry':       'restart_alt',
```

- [ ] **Step 6: Run the test again to confirm it passes**

Run: `npm run test -- --run loopReentryManifest`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the full frontend suite and build**

Run: `npm run test -- --run && npm run build`
Expected: all tests pass, build succeeds with no new errors

- [ ] **Step 8: Commit**

```bash
git add ui/src/types/manifest.ts ui/src/registry/builtinManifests.ts ui/src/lib/categoryStyle.ts ui/src/__tests__/loopReentryManifest.test.tsx
git commit -m "feat(ui): register loop.reentry node type in the frontend registry"
```

---

### Task 3: Delete the synthetic boundary-marker system

**Files:**
- Delete: `ui/src/canvas/nodes/LoopBoundaryNode.tsx`
- Modify: `ui/src/canvas/loop/loopProjection.ts` (remove all boundary-marker code, un-filter the loopBack edge)
- Modify: `ui/src/canvas/Canvas.tsx` (remove import/registration)
- Modify: `ui/src/canvas/edges/edgePresentation.ts` (remove now-unused `isLoopBackEdge`)
- Modify: `ui/src/__tests__/edgePresentation.test.ts` (remove its tests)
- Modify: `ui/src/__tests__/loopProjection.test.ts` (remove marker tests, revert drilled-in assertions to the pre-marker shape)

**Interfaces:**
- Consumes: nothing new.
- Produces: `projectDrilledInView(nodes, edges, loopNodeId)` returns exactly `{ nodes: [guard, ...members], edges: [edges where both endpoints are visible] }` — no synthetic nodes, no loopBack filtering. Task 4's starter-graph assertions are written against this exact (reverted) shape.

- [ ] **Step 1: Update `loopProjection.test.ts` to the target (reverted) shape first**

In `ui/src/__tests__/loopProjection.test.ts`:

Replace the import block:

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
```

Replace the whole `describe('projectDrilledInView on the starter graph', ...)` block (currently lines 114-153) with:

```ts
describe('projectDrilledInView on the starter graph', () => {
  it('shows only the guard and its members, and only the edges between them', () => {
    const { nodes, edges } = loadStarterGraph()
    const { nodes: viewNodes, edges: viewEdges } = projectDrilledInView(nodes, edges, 'loop_guard')

    expect(viewNodes.map((n) => n.id).sort()).toEqual(['loop_guard', 'reasoning', 'review'].sort())
    expect(viewEdges.map((e) => e.id).sort()).toEqual(['e4', 'e6', 'e9'].sort())
  })

  it('is a no-op on nodes/edges when the guard has no loopBack target', () => {
    const { nodes: starterNodes, edges: starterEdges } = loadStarterGraph()
    const edges = starterEdges.filter((e) => !(e.source === 'loop_guard' && e.sourceHandle === 'loopBack'))
    const { nodes: viewNodes } = projectDrilledInView(starterNodes, edges, 'loop_guard')

    expect(viewNodes.map((n) => n.id).sort()).toEqual(['loop_guard'].sort())
  })
})
```

(Note: this deliberately still references the *current*, pre-Task-4 starter graph shape — `e9` going straight `loop_guard -> reasoning`, no `loop_reentry` yet. Task 4 updates this again once the starter graph changes.)

- [ ] **Step 2: Run it to confirm it fails**

Run: `npm run test -- --run loopProjection`
Expected: FAIL — the current code still injects `loop_guard::boundary::start`/`::end` nodes and still filters out `e9`, so both new assertions mismatch, and the `LOOP_BOUNDARY_NODE_TYPE`/`LoopBoundaryNodeData` import no longer exists (TS error) since Step 1 removed it from the import list ahead of the code change.

- [ ] **Step 3: Delete `LoopBoundaryNode.tsx`**

```bash
rm ui/src/canvas/nodes/LoopBoundaryNode.tsx
```

- [ ] **Step 4: Strip the boundary-marker code from `loopProjection.ts`**

Replace the whole file content with:

```ts
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
```

- [ ] **Step 5: Unregister `LoopBoundaryNode` from `Canvas.tsx`**

In `ui/src/canvas/Canvas.tsx`:

Remove the import line:
```ts
import { LoopBoundaryNode } from './nodes/LoopBoundaryNode'
```

Change the loop-projection import from:
```ts
import {
  LOOP_BOUNDARY_NODE_TYPE,
  LOOP_COLLAPSED_NODE_TYPE,
  projectCollapsedView,
  projectDrilledInView,
} from './loop/loopProjection'
```
to:
```ts
import {
  LOOP_COLLAPSED_NODE_TYPE,
  projectCollapsedView,
  projectDrilledInView,
} from './loop/loopProjection'
```

Change the `nodeTypes` `useMemo` body from:
```ts
    map[LOOP_COLLAPSED_NODE_TYPE] = LoopNode
    map[LOOP_BOUNDARY_NODE_TYPE] = LoopBoundaryNode
    return map
```
to:
```ts
    map[LOOP_COLLAPSED_NODE_TYPE] = LoopNode
    return map
```

- [ ] **Step 6: Delete the now-unused `isLoopBackEdge`**

In `ui/src/canvas/edges/edgePresentation.ts`, remove the `LOOP_BACK_HANDLE` constant and the `isLoopBackEdge` function (lines 3, 5-13), leaving:

```ts
const CONDITIONAL_HANDLES = new Set(['accept', 'refine', 'clarify', 'approve', 'revise', 'reject'])

export function edgePresentation(sourceHandle?: string | null) {
  const conditional = Boolean(sourceHandle && CONDITIONAL_HANDLES.has(sourceHandle))
  const color =
    sourceHandle === 'accept' || sourceHandle === 'approve'
      ? '#4edea3'
      : sourceHandle === 'clarify' || sourceHandle === 'revise'
        ? '#ffd180'
        : sourceHandle === 'reject'
          ? '#ff8a80'
          : '#6f8175'

  return { conditional, color }
}
```

In `ui/src/__tests__/edgePresentation.test.ts`, remove the `isLoopBackEdge` import and the whole `describe('isLoopBackEdge', ...)` block (lines 18-29), leaving just the `edgePresentation` describe block and its import (`import { edgePresentation } from '@/canvas/edges/edgePresentation'`).

- [ ] **Step 7: Run the test again to confirm it passes**

Run: `npm run test -- --run`
Expected: all tests pass — `loopProjection.test.ts` matches the reverted shape, no file still imports `LoopBoundaryNode`/`LOOP_BOUNDARY_NODE_TYPE`/`isLoopBackEdge`.

- [ ] **Step 8: Build to catch anything vitest's jsdom run wouldn't**

Run: `npm run build`
Expected: succeeds, no TS errors (repo convention: test passing ≠ build passing, always check both)

- [ ] **Step 9: Commit**

```bash
git add -A -- ui/src/canvas/nodes/LoopBoundaryNode.tsx ui/src/canvas/loop/loopProjection.ts ui/src/canvas/Canvas.tsx ui/src/canvas/edges/edgePresentation.ts ui/src/__tests__/edgePresentation.test.ts ui/src/__tests__/loopProjection.test.ts
git commit -m "refactor(ui): delete synthetic loop boundary marker system"
```

---

### Task 4: Wire `loop.reentry` into the starter graph

**Files:**
- Modify: `ui/src/app/starterArchitecture.ts`
- Modify: `ui/src/__tests__/starterArchitecture.test.ts`
- Modify: `ui/src/__tests__/loopProjection.test.ts` (update the two starter-graph tests written in Task 3 to the new node/edge shape)

**Interfaces:**
- Consumes: `loop.reentry` manifest/type from Tasks 1-2; the reverted `projectDrilledInView`/`projectCollapsedView` from Task 3.
- Produces: none — this is the plan's last functional task.

- [ ] **Step 1: Update `starterArchitecture.test.ts` to the target shape first**

In `ui/src/__tests__/starterArchitecture.test.ts`, replace the test `'reasoning으로 되돌아오는 유일한 피드백 경로가 loop.guard를 거친다'` (currently lines 28-34) with:

```ts
  it('reasoning으로 되돌아오는 유일한 피드백 경로가 loop.guard를 거친다', () => {
    // 가드를 우회하는 되돌림 엣지가 하나라도 있으면 ungated cycle 컴파일 에러가 난다.
    // loop_reentry는 순수 통과 노드이므로 "가드를 거친다"는 곧 "가드 -> loop_reentry -> reasoning"이다.
    const feedbackIntoReasoning = STARTER_ARCHITECTURE.edges
      .filter((e) => e.target === 'reasoning' && !['input', 'planning'].includes(e.source))
      .map((e) => e.source)
    expect(feedbackIntoReasoning).toEqual(['loop_reentry'])

    const reentryInputs = STARTER_ARCHITECTURE.edges
      .filter((e) => e.target === 'loop_reentry')
      .map((e) => e.source)
    expect(reentryInputs).toEqual([guard()!.id])
  })
```

Also update the `'loop.guard의 loopBack/exit 포트가 모두 배선돼 있다'` test's comment is still accurate as-is (no code change needed there — the guard's own outgoing handles are unaffected by what's downstream of `loopBack`).

- [ ] **Step 2: Update the two `loopProjection.test.ts` starter-graph tests**

In `ui/src/__tests__/loopProjection.test.ts`, update the two tests written in Task 3 Step 1:

```ts
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
```

Also update the `describe('projectCollapsedView on the starter graph', ...)` block's second and third tests (member count/ids, and the internal-edge-drop count):

```ts
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
```

(Rename the `it(...)` title on the first of these two — it previously said "2 members"/"3 internal edges"; the code above already uses the corrected titles "3 members"/"4 internal edges".)

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `npm run test -- --run`
Expected: FAIL — `starterArchitecture.ts` doesn't have `loop_reentry` yet, so `feedbackIntoReasoning` is still `['loop_guard']` and the projection tests still see only 2 members / the old edge ids.

- [ ] **Step 4: Add `loop_reentry` to the starter graph**

In `ui/src/app/starterArchitecture.ts`, insert a new node right after `planning` and before `reasoning` in the `nodes` array:

```ts
    { id: 'loop_reentry',      type: 'loop.reentry',        position: { x: 328, y: 380 }, config: {} },
```

Change edge `e9` from:
```ts
    { id: 'e9', source: 'loop_guard',       sourceHandle: 'loopBack', target: 'reasoning',        targetHandle: 'task'   },
```
to:
```ts
    { id: 'e9', source: 'loop_guard',       sourceHandle: 'loopBack', target: 'loop_reentry',     targetHandle: 'in'     },
```

Add a new edge after `e10`:
```ts
    { id: 'e11', source: 'loop_reentry',    sourceHandle: 'out',      target: 'reasoning',        targetHandle: 'task'   },
```

- [ ] **Step 5: Run the tests again to confirm they pass**

Run: `npm run test -- --run`
Expected: all tests pass.

- [ ] **Step 6: Build**

Run: `npm run build`
Expected: succeeds, no new errors.

- [ ] **Step 7: Commit**

```bash
git add ui/src/app/starterArchitecture.ts ui/src/__tests__/starterArchitecture.test.ts ui/src/__tests__/loopProjection.test.ts
git commit -m "feat(ui): demonstrate loop.reentry in the starter graph"
```

---

### Task 5: Final full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd server && ../server/.venv/bin/pytest -q`
Expected: all pass, no warnings about the new node type.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd ui && npm run test -- --run`
Expected: all pass.

- [ ] **Step 3: Build the frontend**

Run: `cd ui && npm run build`
Expected: succeeds.

- [ ] **Step 4: Lint the frontend**

Run: `cd ui && npm run lint`
Expected: only the 3 pre-existing warnings documented in `CLAUDE.local.md` (`TransportContext.tsx`, `NodeLibrary.tsx`, `RegistryContext.tsx`) — no new warnings.

- [ ] **Step 5: Manual smoke check (leave for the user — this sandbox cannot run a browser)**

Note in the final report to the user: `npm run dev`, load the starter graph, double-click the collapsed loop token, and confirm `loop_reentry` renders as a normal circular node (label "Loop Start") between `loop_guard` and `reasoning`, connected by two plain edges — no floating/disconnected marker, no half-capsule shape.
