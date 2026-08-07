# Loop Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the never-executed `LoopPolicy` sidecar with a first-class `loop.guard` canvas node (1 `Feedback` input, `Loop back` / `Exit` outputs) whose config drives the existing 5-axis guard core, make ungated cycles a compile error, delete the dead Loop Scope Lens, and prove the whole thing actually runs — per `docs/superpowers/specs/2026-08-07-loop-node-design.md`.

**Architecture:** `loop.guard` becomes an ordinary manifest-declared node. `compile_graph` registers it like `human.checkpoint` (self-routing via `Command(goto=...)`, skipped in the plain-edge wiring loop) and reads its re-entry/exit targets straight off the node's `loopBack`/`exit` outgoing edges — so edge-reference integrity is structural, not validated. A thin adapter (`_loop_policy_from_config`) reshapes the node's flat config into the nested dict `evaluate_loop_guard` already expects, leaving `server/nodes/loop_guard.py` and `server/tests/test_loop_guard.py` untouched. Budget attribution (`memberNodeIds` in the old design) is derived from graph reachability instead of user declaration. A Python Tarjan SCC port makes any cycle of size ≥ 2 without a `loop.guard` member a `ValueError` at compile time, moving the "don't draw an unbounded loop" guarantee from a frontend view-layer lens into a backend-testable invariant.

**Tech Stack:** Python 3.12, FastAPI, LangGraph `StateGraph`/`Command`, pytest + pytest-asyncio (`asyncio_mode=auto`), ruff; TypeScript 6, Zod 4, Zustand 5, React Flow 12 (`@xyflow/react`), Vitest 4 + Testing Library, oxlint, Vite 8.

## Global Constraints

- **Never merge without executing.** The 8/6 sidecar implementation passed unit tests and type checks and was merged having never been run once (`server/workspace/`'s newest run is dated 7/14). Every task in this plan ends with a real command run and its real output checked; Task 11 additionally runs a live model and a live WebSocket execution.
- Wire-format fields are camelCase on both sides — backend dict keys emitted by `events.py:to_frontend()` match the frontend Zod schema field-for-field, no snake_case leaking (AGENTS.md §4).
- External LLM calls are mocked in every automated test — no network, no real keys (AGENTS.md §6). Live-model execution happens **only** in Task 11's explicit verification steps.
- New backend validation errors are `ValueError` raised at compile time, matching `compile_graph`'s existing style (`"Unknown node type: ..."`, `"Architecture has no entry node..."`).
- Backend verification (from `/home/licodev/projects/agentforge/server`): `.venv/bin/ruff check .` → `.venv/bin/ruff format .` → `.venv/bin/python -m pytest -q`. **Always `python -m pytest`, never the venv's `pytest` binary — its shebang is broken.**
- Frontend verification (from `/home/licodev/projects/agentforge/ui`): `npm run lint` → `npm run test` → `npm run build`. **`npm run build` runs `tsc -b`, which catches errors `tsc --noEmit` misses — it is the final gate, not optional** (recorded in `CLAUDE.local.md`, re-stated in `HANDOFF.md:102`).
- **Do not modify** `server/nodes/loop_guard.py`, `server/tests/test_loop_guard.py`, `server/state.py`, `server/nodes/llm_step.py`. Spec §10 lists these as unchanged-and-reused; `test_loop_guard.py` passing untouched at the end is the regression evidence.
- **Do not modify** `HANDOFF.md`, `start.sh`, `.agents/`, `.opencode/`, `agentforge` — pre-existing uncommitted user work outside this plan's scope (`git status` shows them dirty/untracked).
- Out of scope (spec §비목표): custom canvas renderer for `loop.guard` (GenericNode/AgentNode handle it), `kind: 'retry'`, kind-specific guard presets, self-loop gating, `recursion_limit` re-derivation.
- Default execution model is **`gemini-3.1-flash-lite` (Google)** — `config.yaml:models.default` and `server/main.py:DEFAULT_MODEL_CFG`, and the starter graph pins `modelSlots` to it. Anthropic key health is irrelevant to this plan; `GOOGLE_API_KEY` in `server/.env` is what Task 11's live steps depend on.

---

## Deliberate deviations from the spec (read before starting)

Six places where the spec's literal text needs an adjustment. Each is implemented as written below, not as the spec's snippet reads.

1. **`_loop_policy_from_config` must omit `threshold` when unset.** The spec §3c snippet writes `{"window": ..., "threshold": cfg.get("stuckThreshold")}`, which stores `threshold: None` when the field is blank. `loop_guard.py:58` then does `float(stuck_cfg.get("threshold", 0))` → `float(None)` → `TypeError`. Since `loop_guard.py` is frozen, the adapter omits the key. Covered by a test in Task 3.
2. **The `invalid onExhaustion` compile error is retained.** Spec §9 deletes only the two *edge-reference* errors ("unknown feedbackEdgeId", "mismatched targets") because they became structurally impossible. An out-of-range `onExhaustion` is node-config validation, still possible, and already covered today — it stays.
3. **`ui/src/registry/builtinManifests.ts` also gets the `loop.guard` entry.** Spec §1 names only `server/manifests.py` and the `RUNTIMES` tuple. But `builtinManifests.ts` is the offline fallback that `loadManifests()` returns whenever `/api/nodes` fails *or fails Zod parsing* — omitting `loop.guard` there means the node silently vanishes offline. It is also the reason `RUNTIMES` must be widened: without `'loop_guard'`, `NodeManifestListSchema.parse` throws for the **entire** backend list and `loadManifests` silently falls back to the bundled set.
4. **`useUiStore`'s loop state is deleted too.** Spec §10's deletion list doesn't name `ui/src/stores/useUiStore.ts`, but `expandedLoopScopeIds` / `toggleLoopScopeExpanded` / `hoveredLoopCandidateId` / `setHoveredLoopCandidateId` / `rawExecutionView` / `toggleRawExecutionView` have zero production readers once `LoopScopeNode.tsx`, `LoopAnchor.tsx` and `AgentNode.tsx`'s loop branch are gone (verified by grep: only `__tests__/uiStore.test.ts` remains).
5. **`test_compile_no_entry_raises` must be rewritten.** It currently builds an ungated 2-node cycle (`test_compile.py:81-89`). Once `_validate_gated_cycles` runs before entry detection, it raises `"Cycle without a loop.guard node"` instead of `"no entry"`. Task 7 rewrites it as a *gated* entry-less cycle so it keeps testing what it was written to test.
6. **`test_architecture_without_loop_policies_key_behaves_unchanged` is deleted, not updated.** Its premise (a graph with no `loopPolicies` key) stops existing when the key stops existing. Spec test-plan item 5's replacement intent is split across two Task 7 tests: `test_review_refine_loop_then_accept` (gated loop still produces the same accept/refine/retries outcome) and `test_cycle_without_loop_guard_raises` (the intended breaking change).

---

## File Structure

| File | Change |
| --- | --- |
| `server/manifests.py` | Add the `loop.guard` entry to `BUILTIN_MANIFESTS` between `review.intent` and `human.checkpoint` |
| `server/graphs/compile.py` | Delete `_prepare_loop_policies` (§285-367); add `_handle_targets`, `_loop_policy_from_config`, `_derive_loop_members`, `_tarjan_scc`, `_validate_gated_cycles`; rewrite `compile_graph`'s guard registration + edge wiring; rename one event key in `_make_loop_guard_node` |
| `server/events.py` | Untouched (`loop_runtime` is an opaque dict) |
| `server/nodes/loop_guard.py`, `server/state.py`, `server/nodes/llm_step.py`, `server/nodes/review.py` | **Untouched** (`loop_policy_ids` param name deliberately retained per spec §3d) |
| `server/tests/test_manifests.py` | Add `loop.guard` manifest-shape test |
| `server/tests/test_events.py` | `loopPolicyId` → `loopNodeId` |
| `server/tests/test_compile.py` | Delete `_loop_policy` fixture + 6 sidecar tests; add node-based loop tests, SCC tests, member-derivation tests, adapter tests; rewrite 2 existing tests |
| `server/tests/test_ws_starter_graph.py` (new) | End-to-end `/ws/run` run of the starter graph with a `loop.guard` in it |
| `ui/src/types/manifest.ts` | `RUNTIMES` += `'loop_guard'` |
| `ui/src/registry/builtinManifests.ts` | Add the `loop.guard` manifest, options sourced from `LOOP_POLICY_KINDS` / `LOOP_POLICY_EXHAUSTION_ACTIONS` |
| `ui/src/types/events.ts` | `LoopRuntimeSchema.loopPolicyId` → `loopNodeId`; drop the `progress` field |
| `ui/src/types/graph.ts` | Delete `LoopPolicyGuardSchema`, `LoopPolicySchema`, `ArchitectureSchema.loopPolicies`; keep the two const arrays |
| `ui/src/stores/useGraphStore.ts` | Drop `loopPolicies` state + round-trip |
| `ui/src/stores/useUiStore.ts` | Drop the six dead loop-lens state members |
| `ui/src/canvas/Canvas.tsx`, `ui/src/panels/Inspector.tsx`, `ui/src/canvas/nodes/AgentNode.tsx` | Remove Lens imports/branches |
| 13 source + 8 test files under `ui/src/canvas/loops/`, `ui/src/canvas/nodes/`, `ui/src/panels/` | **Deleted** (~1,790 lines) |
| `ui/src/app/starterArchitecture.ts` | Drop `loopPolicies`; add a `loop.guard` node on the refine loop |
| `ui/src/__tests__/loopGuardManifest.test.tsx`, `ui/src/__tests__/starterArchitecture.test.ts` (new) | Manifest shape + GenericNode render; starter graph wiring |
| `ui/src/__tests__/loopPolicy.schema.test.ts` | **Deleted** |
| `ui/src/__tests__/graphStore.test.ts`, `events.schema.test.ts`, `uiStore.test.ts` | Drop sidecar/lens assertions |

---

### Task 1: `loop.guard` node manifest (backend + frontend registry)

**Files:**
- Modify: `server/manifests.py:168` (insert a new dict after the `review.intent` entry, before `human.checkpoint`)
- Modify: `ui/src/types/manifest.ts:55`
- Modify: `ui/src/registry/builtinManifests.ts:1` (imports) and `:197` (insert after `review.intent`)
- Test: `server/tests/test_manifests.py`
- Test: `ui/src/__tests__/loopGuardManifest.test.tsx` (create)

**Interfaces:**
- Produces: node type id `"loop.guard"`; runtime id `"loop_guard"`; category `"policy"`; input port id `"in"`; output port ids `"loopBack"`, `"exit"`; config keys in order `kind, maxIterations, maxTokens, maxCostUsd, maxDurationSec, stuckWindow, stuckThreshold, onExhaustion`. Every later task depends on these exact strings.
- Consumes: `LOOP_POLICY_KINDS` and `LOOP_POLICY_EXHAUSTION_ACTIONS` (already exported from `ui/src/types/graph.ts:43-44`).

- [ ] **Step 1: Write the failing backend manifest test**

Append to `server/tests/test_manifests.py`:

```python
def test_loop_guard_manifest_declares_one_feedback_input_and_two_outputs(client):
    manifests = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert "loop.guard" in manifests, "loop.guard 매니페스트가 /api/nodes에 없다"

    loop = manifests["loop.guard"]
    assert loop["runtime"] == "loop_guard"
    assert loop["category"] == "policy"
    assert [(p["id"], p["label"]) for p in loop["inputs"]] == [("in", "Feedback")]
    assert [(p["id"], p["label"]) for p in loop["outputs"]] == [
        ("loopBack", "Loop back"),
        ("exit", "Exit"),
    ]


def test_loop_guard_manifest_exposes_all_five_guard_axes(client):
    manifests = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert [c["key"] for c in manifests["loop.guard"]["config"]] == [
        "kind",
        "maxIterations",
        "maxTokens",
        "maxCostUsd",
        "maxDurationSec",
        "stuckWindow",
        "stuckThreshold",
        "onExhaustion",
    ]
```

- [ ] **Step 2: Run it to see it fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_manifests.py -q
```
Expected: 2 failures, `AssertionError: loop.guard 매니페스트가 /api/nodes에 없다`.

- [ ] **Step 3: Add the backend manifest**

In `server/manifests.py`, insert this dict immediately after the closing `},` of the `review.intent` entry (currently line 168) and before the `human.checkpoint` entry:

```python
    {
        "type": "loop.guard",
        "runtime": "loop_guard",
        "category": "policy",
        "label": "Loop",
        "description": "루프 재진입/탈출 지점과 5축 가드(iteration/token/cost/duration/stuck)를 정의.",
        "inputs": [{"id": "in", "label": "Feedback", "dataType": "any", "required": True}],
        "outputs": [
            {"id": "loopBack", "label": "Loop back", "dataType": "any"},
            {"id": "exit", "label": "Exit", "dataType": "any"},
        ],
        "config": [
            {
                "key": "kind",
                "label": "Kind",
                "type": "select",
                "default": "critiqueRevise",
                "options": [
                    {"label": "Evaluator-Optimizer", "value": "evaluatorOptimizer"},
                    {"label": "Critique-Revise", "value": "critiqueRevise"},
                    {"label": "Human Review", "value": "humanReview"},
                ],
                "description": "서술 전용 — 컴파일러 라우팅/가드 판정에는 쓰이지 않는다.",
            },
            {"key": "maxIterations", "label": "Max iterations", "type": "number"},
            {"key": "maxTokens", "label": "Max tokens", "type": "number"},
            {"key": "maxCostUsd", "label": "Max cost (USD)", "type": "number"},
            {"key": "maxDurationSec", "label": "Max duration (sec)", "type": "number"},
            {"key": "stuckWindow", "label": "Stuck window", "type": "number"},
            {"key": "stuckThreshold", "label": "Stuck threshold", "type": "number"},
            {
                "key": "onExhaustion",
                "label": "On exhaustion",
                "type": "select",
                "default": "exit",
                "options": [
                    {"label": "Exit", "value": "exit"},
                    {"label": "Escalate", "value": "escalate"},
                    {"label": "Fail", "value": "fail"},
                ],
            },
        ],
    },
```

- [ ] **Step 4: Run the backend test to verify it passes**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_manifests.py -q
```
Expected: all pass.

- [ ] **Step 5: Write the failing frontend manifest + render test**

Create `ui/src/__tests__/loopGuardManifest.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { BUILTIN_MANIFESTS } from '@/registry/builtinManifests'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { GenericNode } from '@/canvas/nodes/GenericNode'
import {
  LOOP_POLICY_EXHAUSTION_ACTIONS,
  LOOP_POLICY_KINDS,
  NodeManifestListSchema,
} from '@/types'

const loopGuard = BUILTIN_MANIFESTS.find((m) => m.type === 'loop.guard')!

describe('loop.guard 매니페스트', () => {
  it('Feedback 입력 1개와 Loop back / Exit 출력 2개를 선언한다', () => {
    expect(loopGuard).toBeDefined()
    expect(loopGuard.inputs.map((p) => [p.id, p.label])).toEqual([['in', 'Feedback']])
    expect(loopGuard.outputs.map((p) => [p.id, p.label])).toEqual([
      ['loopBack', 'Loop back'],
      ['exit', 'Exit'],
    ])
  })

  it("runtime 'loop_guard'가 NodeManifestSchema를 통과한다", () => {
    // RUNTIMES에 'loop_guard'가 없으면 loadManifests()가 백엔드 목록 전체를 조용히
    // 버리고 번들 폴백으로 떨어진다 — 그 회귀를 여기서 막는다.
    expect(() => NodeManifestListSchema.parse(BUILTIN_MANIFESTS)).not.toThrow()
    expect(loopGuard.runtime).toBe('loop_guard')
    expect(loopGuard.category).toBe('policy')
  })

  it('5축 guard config 필드를 순서대로 노출한다', () => {
    expect(loopGuard.config.map((f) => f.key)).toEqual([
      'kind',
      'maxIterations',
      'maxTokens',
      'maxCostUsd',
      'maxDurationSec',
      'stuckWindow',
      'stuckThreshold',
      'onExhaustion',
    ])
  })

  it('kind/onExhaustion 옵션 값이 공유 상수에서 나온다', () => {
    const values = (key: string) =>
      loopGuard.config.find((f) => f.key === key)?.options?.map((o) => o.value)
    expect(values('kind')).toEqual([...LOOP_POLICY_KINDS])
    expect(values('onExhaustion')).toEqual([...LOOP_POLICY_EXHAUSTION_ACTIONS])
  })
})

describe('loop.guard 렌더링', () => {
  it('커스텀 렌더러 없이 GenericNode가 두 출력 포트를 그린다', () => {
    const registry = new NodeRegistry(BUILTIN_MANIFESTS)
    expect(registry.customComponent('loop.guard')).toBeUndefined()

    const props = {
      id: 'loop-1',
      type: 'loop.guard',
      data: { manifestType: 'loop.guard', config: {} },
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

    expect(screen.getByText('Loop')).toBeInTheDocument()
    expect(screen.getByText('Feedback')).toBeInTheDocument()
    expect(screen.getByText('Loop back')).toBeInTheDocument()
    expect(screen.getByText('Exit')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run it to see it fail**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- loopGuardManifest
```
Expected: fails — `loopGuard` is `undefined`, `TypeError: Cannot read properties of undefined (reading 'inputs')`.

- [ ] **Step 7: Widen the `RUNTIMES` tuple**

In `ui/src/types/manifest.ts`, replace line 55:

```ts
const RUNTIMES = ['llm_step', 'policy', 'review', 'checkpoint', 'model', 'io', 'loop_guard'] as const
```

- [ ] **Step 8: Add the bundled frontend manifest**

In `ui/src/registry/builtinManifests.ts`, replace the import line 1 with:

```ts
import {
  LOOP_POLICY_EXHAUSTION_ACTIONS,
  LOOP_POLICY_KINDS,
  type NodeManifest,
} from '@/types'

const LOOP_KIND_LABELS: Record<(typeof LOOP_POLICY_KINDS)[number], string> = {
  evaluatorOptimizer: 'Evaluator-Optimizer',
  critiqueRevise: 'Critique-Revise',
  humanReview: 'Human Review',
}

const LOOP_EXHAUSTION_LABELS: Record<(typeof LOOP_POLICY_EXHAUSTION_ACTIONS)[number], string> = {
  exit: 'Exit',
  escalate: 'Escalate',
  fail: 'Fail',
}
```

Then insert this entry immediately after the `review.intent` entry's closing `},` (currently line 197), before the `// ── Human ──` comment:

```ts
  // ── Policy / Loop ──────────────────────────────────────────────────────────

  {
    type: 'loop.guard',
    runtime: 'loop_guard',
    category: 'policy',
    label: 'Loop',
    description: '루프 재진입/탈출 지점과 5축 가드(iteration/token/cost/duration/stuck)를 정의.',
    inputs: [{ id: 'in', label: 'Feedback', dataType: 'any', required: true }],
    outputs: [
      { id: 'loopBack', label: 'Loop back', dataType: 'any' },
      { id: 'exit',     label: 'Exit',      dataType: 'any' },
    ],
    config: [
      {
        key: 'kind',
        label: 'Kind',
        type: 'select',
        default: 'critiqueRevise',
        options: LOOP_POLICY_KINDS.map((value) => ({ label: LOOP_KIND_LABELS[value], value })),
        description: '서술 전용 — 컴파일러 라우팅/가드 판정에는 쓰이지 않는다.',
      },
      { key: 'maxIterations',  label: 'Max iterations',     type: 'number' },
      { key: 'maxTokens',      label: 'Max tokens',         type: 'number' },
      { key: 'maxCostUsd',     label: 'Max cost (USD)',     type: 'number' },
      { key: 'maxDurationSec', label: 'Max duration (sec)', type: 'number' },
      { key: 'stuckWindow',    label: 'Stuck window',       type: 'number' },
      { key: 'stuckThreshold', label: 'Stuck threshold',    type: 'number' },
      {
        key: 'onExhaustion',
        label: 'On exhaustion',
        type: 'select',
        default: 'exit',
        options: LOOP_POLICY_EXHAUSTION_ACTIONS.map((value) => ({
          label: LOOP_EXHAUSTION_LABELS[value],
          value,
        })),
      },
    ],
  },
```

- [ ] **Step 9: Run the frontend test to verify it passes**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- loopGuardManifest
```
Expected: 5 passed.

- [ ] **Step 10: Prove it actually runs — the node reaches a live `/api/nodes` and type-checks**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .
cd /home/licodev/projects/agentforge/server && .venv/bin/python -c "
from fastapi.testclient import TestClient
from main import app
with TestClient(app) as c:
    types = [n['type'] for n in c.get('/api/nodes').json()]
print(types)
assert 'loop.guard' in types
"
cd /home/licodev/projects/agentforge/ui && npm run lint && npm run build
```
Expected: the printed list contains `'loop.guard'`; `npm run build` succeeds (only the pre-existing >500 kB chunk-size warning).

- [ ] **Step 11: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/manifests.py server/tests/test_manifests.py ui/src/types/manifest.ts ui/src/registry/builtinManifests.ts ui/src/__tests__/loopGuardManifest.test.tsx && git commit -m "feat: add loop.guard node manifest to backend and frontend registry"
```

---

### Task 2: Rename the event field `loopPolicyId` → `loopNodeId`

Doing this first (while the sidecar is still wired) keeps every test written in Tasks 3-7 on the final field name.

**Files:**
- Modify: `server/graphs/compile.py:391`
- Modify: `ui/src/types/events.ts:65-79`
- Test: `server/tests/test_events.py:34-48`
- Test: `ui/src/__tests__/events.schema.test.ts:56-72`

**Interfaces:**
- Produces: `loopRuntime.loopNodeId: string` on the WebSocket event contract (value = the real canvas node id). `LoopRuntimeSchema` no longer has a `progress` field.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Rewrite the backend event test to the new name**

In `server/tests/test_events.py`, replace `test_to_frontend_includes_loop_runtime_camelcase` (lines 33-46) with:

```python
def test_to_frontend_includes_loop_runtime_camelcase():
    ev = make_event(
        "run-1",
        "loop_guard",
        "node_end",
        loop_runtime={"loopNodeId": "loop_guard", "iteration": 2, "exitReason": "maxIterations"},
    )
    payload = ev.to_frontend()

    assert payload["loopRuntime"] == {
        "loopNodeId": "loop_guard",
        "iteration": 2,
        "exitReason": "maxIterations",
    }
    # 가드 이벤트의 nodeId가 곧 loopNodeId — 프론트는 일반 노드와 같은 방식으로 소비한다.
    assert payload["nodeId"] == payload["loopRuntime"]["loopNodeId"]
```

- [ ] **Step 2: Run it — it passes (events.py is field-agnostic), so verify the *compiler* is what still emits the old key**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_events.py -q
grep -n "loopPolicyId" graphs/compile.py
```
Expected: tests pass; `grep` prints `391:            "loopPolicyId": policy_id,` — that is the line to change.

- [ ] **Step 3: Rename the key in the compiler**

In `server/graphs/compile.py`, inside `_make_loop_guard_node`, change line 391 from `"loopPolicyId": policy_id,` to:

```python
            "loopNodeId": policy_id,
```

- [ ] **Step 4: Run the full backend suite to confirm nothing else read the old key**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest -q && grep -rn "loopPolicyId" . --include="*.py"
```
Expected: all tests pass; `grep` prints nothing (exit code 1).

- [ ] **Step 5: Rewrite the frontend event test**

In `ui/src/__tests__/events.schema.test.ts`, replace the `'loopRuntime 필드를 보존한다'` test (lines 56-72) with:

```ts
  it('loopRuntime 필드를 보존한다 (loopNodeId = 실제 캔버스 노드 id)', () => {
    const payload = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: 'loop_guard',
      timestamp: new Date().toISOString(),
      loopRuntime: {
        loopNodeId: 'loop_guard',
        iteration: 2,
        maxIterations: 5,
        exitReason: 'maxIterations',
      },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.loopRuntime?.loopNodeId).toBe('loop_guard')
    expect(parsed.loopRuntime?.exitReason).toBe('maxIterations')
  })

  it('loopPolicyId만 담긴 구(舊) 페이로드는 거부한다', () => {
    const legacy = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: '__loop_guard__loop-1',
      timestamp: new Date().toISOString(),
      loopRuntime: { loopPolicyId: 'loop-1', iteration: 1 },
    }
    expect(() => ExecutionEventSchema.parse(legacy)).toThrow()
  })
```

- [ ] **Step 6: Run it to see it fail**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- events.schema
```
Expected: `loopNodeId` test fails (`Invalid input: expected string, received undefined` at `loopRuntime.loopPolicyId`); the legacy-rejection test passes for the wrong reason.

- [ ] **Step 7: Rename the field in the Zod schema and drop `progress`**

In `ui/src/types/events.ts`, replace lines 65-80 with:

```ts
/** Per-pass snapshot emitted by a `loop.guard` canvas node — see
 * docs/superpowers/specs/2026-08-07-loop-node-design.md §8. `loopNodeId` is the
 * real canvas node id, identical to the event's own `nodeId`, so consumers can
 * treat guard events exactly like any other node's events. */
export const LoopRuntimeSchema = z.object({
  loopNodeId: z.string(),
  iteration: z.number(),
  maxIterations: z.number().optional(),
  tokens: z.number().optional(),
  costUsd: z.number().optional(),
  durationMs: z.number().optional(),
  lastFeedback: z.string().optional(),
  exitReason: z.enum(LOOP_RUNTIME_EXIT_REASONS).optional(),
})
export type LoopRuntime = z.infer<typeof LoopRuntimeSchema>
```

- [ ] **Step 8: Run the frontend gates**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test && npm run lint && npm run build
```
Expected: all tests pass; lint clean; build succeeds.

- [ ] **Step 9: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_events.py ui/src/types/events.ts ui/src/__tests__/events.schema.test.ts && git commit -m "refactor: rename loopRuntime.loopPolicyId to loopNodeId and drop unused progress field"
```

---

### Task 3: `_loop_policy_from_config` — flat node config → nested guard dict

**Files:**
- Modify: `server/graphs/compile.py` (add a function above `_make_loop_guard_node`, i.e. before current line 370)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Produces: `_loop_policy_from_config(node: dict) -> dict` returning `{"id": <node id>, "onExhaustion": str, "guard": dict}` — exactly the shape `nodes.loop_guard.evaluate_loop_guard(policy, runtime)` already consumes. Tasks 6 and 7 call it.
- Consumes: the config keys defined in Task 1.

- [ ] **Step 1: Write the failing adapter tests**

In `server/tests/test_compile.py`, extend the import block at the top (lines 3-9) to:

```python
import pytest
from langgraph.types import Command

import graphs.compile as compile_mod
import nodes.review as review_mod
from events import ListEventEmitter
from nodes.loop_guard import evaluate_loop_guard
from state import empty_loop_runtime, initial_state
```

and append these tests at the end of the file:

```python
def test_loop_policy_from_config_nests_the_four_scalar_axes():
    node = _node(
        "guard",
        "loop.guard",
        {
            "kind": "critiqueRevise",
            "maxIterations": 3,
            "maxTokens": 1000,
            "maxCostUsd": 0.5,
            "maxDurationSec": 60,
            "onExhaustion": "escalate",
        },
    )
    assert compile_mod._loop_policy_from_config(node) == {
        "id": "guard",
        "onExhaustion": "escalate",
        "guard": {
            "maxIterations": 3,
            "maxTokens": 1000,
            "maxCostUsd": 0.5,
            "maxDurationSec": 60,
        },
    }


def test_loop_policy_from_config_defaults_to_exit_with_an_empty_guard():
    assert compile_mod._loop_policy_from_config(_node("guard", "loop.guard", {})) == {
        "id": "guard",
        "onExhaustion": "exit",
        "guard": {},
    }


def test_loop_policy_from_config_nests_stuck_window_and_threshold():
    node = _node("guard", "loop.guard", {"stuckWindow": 3, "stuckThreshold": 1})
    assert compile_mod._loop_policy_from_config(node)["guard"] == {
        "stuck": {"window": 3, "threshold": 1}
    }


def test_loop_policy_from_config_omits_stuck_threshold_when_unset():
    """threshold를 None으로 채워 넣으면 loop_guard._is_stuck의 float(None)이 TypeError를
    낸다 — 미설정이면 키 자체를 빼서 그쪽 기본값(0)이 살아나야 한다.
    (loop_guard.py는 무변경 대상이므로 이 어댑터가 계약을 맞춰줘야 한다.)"""
    guard = compile_mod._loop_policy_from_config(
        _node("guard", "loop.guard", {"stuckWindow": 3})
    )["guard"]

    assert guard == {"stuck": {"window": 3}}
    assert evaluate_loop_guard(
        {"guard": guard},
        {**empty_loop_runtime(), "iteration": 3, "progress_history": [4.0, 4.0, 4.0]},
    ) == {"should_continue": False, "exit_reason": "stuck"}
```

- [ ] **Step 2: Run them to see them fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k loop_policy_from_config -q
```
Expected: 4 failures, `AttributeError: module 'graphs.compile' has no attribute '_loop_policy_from_config'`.

- [ ] **Step 3: Implement the adapter**

In `server/graphs/compile.py`, insert immediately above `def _make_loop_guard_node(` (currently line 370):

```python
_SCALAR_GUARD_KEYS = ("maxIterations", "maxTokens", "maxCostUsd", "maxDurationSec")


def _loop_policy_from_config(node: dict) -> dict:
    """loop.guard 노드의 평평한 config를 evaluate_loop_guard가 기대하는 중첩 dict로 재조립.

    이 어댑터가 있어서 nodes/loop_guard.py(순수 가드 평가 코어)는 캔버스 노드
    계약을 전혀 모른 채 그대로 재사용된다. stuckThreshold가 비어 있으면 키 자체를
    넣지 않는다 — None을 넣으면 _is_stuck의 float(None)이 TypeError가 된다.
    """
    cfg = node.get("config") or {}
    guard: dict = {key: cfg[key] for key in _SCALAR_GUARD_KEYS if cfg.get(key) is not None}
    if cfg.get("stuckWindow") is not None:
        stuck: dict = {"window": cfg["stuckWindow"]}
        if cfg.get("stuckThreshold") is not None:
            stuck["threshold"] = cfg["stuckThreshold"]
        guard["stuck"] = stuck
    return {"id": node["id"], "onExhaustion": cfg.get("onExhaustion", "exit"), "guard": guard}
```

- [ ] **Step 4: Run them to verify they pass**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k loop_policy_from_config -q
```
Expected: 4 passed.

- [ ] **Step 5: Run the whole backend suite and lint**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/python -m pytest -q
```
Expected: everything passes (the sidecar path is still intact at this point).

- [ ] **Step 6: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_compile.py && git commit -m "feat(server): add _loop_policy_from_config adapter for loop.guard node config"
```

---

### Task 4: `_derive_loop_members` — budget attribution from graph reachability

**Files:**
- Modify: `server/graphs/compile.py` (add above `_loop_policy_from_config`)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Produces: `_derive_loop_members(loop_node_id: str, continue_target: str | None, outgoing: dict[str, list[dict]]) -> set[str]`. Task 6 uses it to build the `node_to_policies` reverse index passed to `_make_llm_step_node` / `_make_review_node` as `loop_policy_ids`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing derivation tests**

Append to `server/tests/test_compile.py`:

```python
def _outgoing(edges: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in edges:
        out.setdefault(e["source"], []).append(e)
    return out


def test_derive_loop_members_returns_only_the_refine_loop_body():
    """스타터 그래프 모양: input/output/checkpoint처럼 가드로 되돌아오지 않는 노드는
    예산 귀속 대상이 아니다."""
    edges = [
        _edge("input", "reasoning", "task"),
        _edge("reasoning", "review", "answer"),
        _edge("review", "guard", "refine", "in"),
        _edge("review", "output", "accept", "result"),
        _edge("review", "checkpoint", "clarify", "review"),
        _edge("guard", "reasoning", "loopBack", "task"),
        _edge("guard", "output", "exit", "result"),
        _edge("checkpoint", "output", "approve", "result"),
    ]
    members = compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges))
    assert members == {"reasoning", "review"}


def test_derive_loop_members_covers_a_three_node_body():
    edges = [
        _edge("reasoning", "critic", "answer"),
        _edge("critic", "review", "critique"),
        _edge("review", "guard", "refine", "in"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    assert compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges)) == {
        "reasoning",
        "critic",
        "review",
    }


def test_derive_loop_members_is_empty_without_a_loop_back_target():
    assert compile_mod._derive_loop_members("guard", None, {}) == set()


def test_derive_loop_members_excludes_a_dead_end_branch_inside_the_loop_body():
    """루프 안에서 갈라져 나가지만 가드로 되돌아오지 않는 가지는 제외된다."""
    edges = [
        _edge("reasoning", "review", "answer"),
        _edge("review", "guard", "refine", "in"),
        _edge("review", "sink", "accept", "result"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    assert compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges)) == {
        "reasoning",
        "review",
    }
```

- [ ] **Step 2: Run them to see them fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k derive_loop_members -q
```
Expected: 4 failures, `AttributeError: module 'graphs.compile' has no attribute '_derive_loop_members'`.

- [ ] **Step 3: Implement the derivation**

In `server/graphs/compile.py`, insert immediately above `_SCALAR_GUARD_KEYS`:

```python
def _derive_loop_members(
    loop_node_id: str, continue_target: str | None, outgoing: dict[str, list[dict]]
) -> set[str]:
    """loopBack 타깃에서 출발해 다시 그 loop.guard 노드로 돌아오는 노드 집합 = 루프 본체.

    8/6 sidecar 설계의 사용자 선언 memberNodeIds를 그래프 도달 가능성으로 유도하는
    것으로 대체한다(설계 §3d). 토큰/비용 예산을 어떤 노드에 귀속시킬지 결정한다.
    """
    if continue_target is None:
        return set()

    # 전방: continue_target에서 도달 가능한 노드 (가드 자신은 경계이므로 넘지 않는다)
    forward: set[str] = set()
    stack = [continue_target]
    while stack:
        current = stack.pop()
        if current == loop_node_id or current in forward:
            continue
        forward.add(current)
        stack.extend(e["target"] for e in outgoing.get(current, []))

    # 후방: 가드로 되돌아올 수 있는 노드
    reverse: dict[str, list[str]] = {}
    for source, edge_list in outgoing.items():
        for e in edge_list:
            reverse.setdefault(e["target"], []).append(source)

    backward: set[str] = set()
    stack = [loop_node_id]
    while stack:
        current = stack.pop()
        if current in backward:
            continue
        backward.add(current)
        stack.extend(reverse.get(current, []))

    return forward & backward
```

- [ ] **Step 4: Run them to verify they pass**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k derive_loop_members -q
```
Expected: 4 passed.

- [ ] **Step 5: Lint, format, full suite**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/python -m pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_compile.py && git commit -m "feat(server): derive loop budget members from graph reachability"
```

---

### Task 5: Tarjan SCC port + `_validate_gated_cycles` (pure, not yet wired)

**Files:**
- Modify: `server/graphs/compile.py` (add above `_derive_loop_members`)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Produces: `_tarjan_scc(node_ids: list[str], edges: list[dict]) -> list[list[str]]` and `_validate_gated_cycles(node_ids: list[str], edges: list[dict], loop_node_ids: set[str]) -> None` (raises `ValueError`). Task 7 wires the latter into `compile_graph`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing SCC + validation tests**

Append to `server/tests/test_compile.py` (the cases are ported from the frontend Lens tests in `ui/src/__tests__/loopCandidates.test.ts:8-57`, which Task 9 deletes):

```python
def _scc_sorted(components: list[list[str]]) -> list[list[str]]:
    return sorted(sorted(component) for component in components)


def test_tarjan_scc_isolates_every_node_when_there_are_no_edges():
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], [])) == [["a"], ["b"], ["c"]]


def test_tarjan_scc_does_not_merge_a_one_way_chain():
    edges = [_edge("a", "b"), _edge("b", "c")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], edges)) == [["a"], ["b"], ["c"]]


def test_tarjan_scc_merges_a_simple_two_cycle():
    edges = [_edge("a", "b"), _edge("b", "a")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b"], edges)) == [["a", "b"]]


def test_tarjan_scc_keeps_a_self_loop_as_a_size_one_component():
    assert _scc_sorted(compile_mod._tarjan_scc(["a"], [_edge("a", "a")])) == [["a"]]


def test_tarjan_scc_merges_two_cycles_that_share_a_node():
    edges = [_edge("a", "b"), _edge("b", "a"), _edge("a", "c"), _edge("c", "a")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], edges)) == [["a", "b", "c"]]


def test_validate_gated_cycles_raises_for_an_ungated_cycle():
    with pytest.raises(ValueError, match="Cycle without a loop.guard node"):
        compile_mod._validate_gated_cycles(
            ["a", "b"], [_edge("a", "b"), _edge("b", "a")], set()
        )


def test_validate_gated_cycles_accepts_a_cycle_containing_a_guard():
    compile_mod._validate_gated_cycles(["a", "g"], [_edge("a", "g"), _edge("g", "a")], {"g"})


def test_validate_gated_cycles_ignores_self_loops():
    """SCC 크기 1(self-loop 포함)은 게이팅 대상이 아니다 (설계 §비목표)."""
    compile_mod._validate_gated_cycles(["a"], [_edge("a", "a")], set())


def test_validate_gated_cycles_reports_only_the_ungated_component():
    edges = [
        _edge("a", "g"),
        _edge("g", "a"),
        _edge("c", "d"),
        _edge("d", "c"),
    ]
    with pytest.raises(ValueError, match=r"\['c', 'd'\]"):
        compile_mod._validate_gated_cycles(["a", "g", "c", "d"], edges, {"g"})
```

- [ ] **Step 2: Run them to see them fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k "tarjan or gated_cycles" -q
```
Expected: 9 failures, `AttributeError: module 'graphs.compile' has no attribute '_tarjan_scc'`.

- [ ] **Step 3: Implement the SCC port and the validator**

In `server/graphs/compile.py`, insert immediately above `_derive_loop_members`:

```python
def _tarjan_scc(node_ids: list[str], edges: list[dict]) -> list[list[str]]:
    """Tarjan SCC. 크기 >= 2인 컴포넌트는 그 안에 최소 하나의 cycle이 있다는 뜻이다.

    ui/src/canvas/loops/loopCandidates.ts의 findStronglyConnectedComponents를
    포팅한 것 — Tier 판별용 countSimpleCyclesCapped는 UI 표시 목적이 사라져
    포팅하지 않는다(설계 §4).
    """
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for e in edges:
        if e["source"] in adjacency:
            adjacency[e["source"]].append(e["target"])

    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []

    def strong_connect(v: str) -> None:
        nonlocal index_counter
        indices[v] = index_counter
        lowlink[v] = index_counter
        index_counter += 1
        stack.append(v)
        on_stack.add(v)

        for w in adjacency.get(v, []):
            if w not in indices:
                strong_connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node_id in node_ids:
        if node_id not in indices:
            strong_connect(node_id)

    return components


def _validate_gated_cycles(
    node_ids: list[str], edges: list[dict], loop_node_ids: set[str]
) -> None:
    """가드 없이 그려진 cycle은 컴파일 에러 — 무한 루프를 멈출 지점이 없다는 뜻이다.

    프론트 Loop Scope Lens가 담당하던 실수 방지 역할의 백엔드 이관(설계 §4).
    크기 1 컴포넌트(self-loop 포함)는 대상이 아니다.
    """
    for component in _tarjan_scc(node_ids, edges):
        if len(component) >= 2 and not (set(component) & loop_node_ids):
            raise ValueError(
                f"Cycle without a loop.guard node: {sorted(component)} — "
                "add a Loop node on the feedback edge"
            )
```

- [ ] **Step 4: Run them to verify they pass**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k "tarjan or gated_cycles" -q
```
Expected: 9 passed.

- [ ] **Step 5: Lint, format, full suite (validation is still unwired, so nothing else changes)**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/python -m pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_compile.py && git commit -m "feat(server): port Tarjan SCC and add ungated-cycle validator"
```

---

### Task 6: Wire `loop.guard` into `compile_graph`; delete `_prepare_loop_policies`

The big one: this is the task that replaces the sidecar. Cycle validation is deliberately **not** enabled yet (Task 7) so this task's diff stays about routing.

**Files:**
- Modify: `server/graphs/compile.py:285-367` (delete `_prepare_loop_policies`), `:370-415` (`_make_loop_guard_node` message), `:418-531` (`compile_graph`)
- Test: `server/tests/test_compile.py:42-54` (delete `_loop_policy`), `:300-403` (delete 4, replace 2), `:406-674` (replace 5)

**Interfaces:**
- Consumes: `_loop_policy_from_config` (Task 3), `_derive_loop_members` (Task 4), the manifest port ids `loopBack`/`exit` (Task 1), `loopNodeId` (Task 2).
- Produces: `_handle_targets(outgoing: dict[str, list[dict]], node_id: str) -> dict[str, str]`. `compile_graph` no longer reads `architecture["loopPolicies"]` at all. Guard events are emitted under the real canvas node id.

- [ ] **Step 1: Delete the six sidecar tests and the `_loop_policy` fixture**

In `server/tests/test_compile.py` delete:
- the `_loop_policy` helper (lines 42-54),
- `test_loop_policy_unknown_feedback_edge_raises` (300-308) — structurally impossible now (§9),
- `test_loop_policy_feedback_edge_wrong_source_type_raises` (311-320) — the v1 node-type whitelist is gone (§목표 2),
- `test_loop_policy_mismatched_feedback_targets_raises` (323-337) — a node has exactly one input port (§9),
- `test_loop_policy_missing_id_raises` (383-403) — the node id is structural,
- `test_loop_policy_exit_without_exit_edges_raises` (340-356) and `test_loop_policy_invalid_on_exhaustion_raises` (359-380) — replaced in Step 2,
- `test_loop_policy_max_iterations_trips_to_exit` (406-454), `test_loop_policy_on_exhaustion_fail_raises` (457-496), `test_loop_policy_max_tokens_trips_to_exit` (499-554), `test_loop_policy_on_human_checkpoint_feedback_edge_reaches_guard_via_dynamic_goto` (557-618), `test_loop_policy_stuck_trips_to_exit` (621-674) — replaced in Step 2.

Leave `test_architecture_without_loop_policies_key_behaves_unchanged` (677-720) alone for now; Task 7 removes it.

- [ ] **Step 2: Write the failing node-based loop tests**

Add this shared fixture builder right after the `_delta` helper (which ends at line 39):

```python
def _gated_refine_arch(guard_config: dict, review_config: dict | None = None) -> dict:
    """스타터 그래프와 같은 모양의 게이팅된 refine 루프.

        input → reasoning → review
        review --refine--> guard --loopBack--> reasoning
        review --accept--> output      guard --exit--> output
    """
    return _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", review_config or {"maxRetries": 10}),
            _node("guard", "loop.guard", {"onExhaustion": "exit", **guard_config}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
        ],
    )


async def _always_unmet(state, *, node_id, **kwargs):
    return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])


_ONE_CRITERION = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
```

Then append these tests at the end of the file:

```python
async def test_loop_guard_without_a_loop_back_edge_raises(monkeypatch):
    """loopBack이 배선 안 된 Loop 노드는 '아무 데도 안 도는 루프' — 설정 실수다 (§9)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("guard", "loop.guard", {"onExhaustion": "fail"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
        ],
    )
    with pytest.raises(ValueError, match="no 'loopBack' edge"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_exit_port_unwired_raises(monkeypatch):
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
        ],
    )
    with pytest.raises(ValueError, match="requires a wired 'exit' port"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_invalid_on_exhaustion_raises(monkeypatch):
    _patch_model(monkeypatch)
    arch = _gated_refine_arch({"onExhaustion": "retry-forever"})
    with pytest.raises(ValueError, match="invalid onExhaustion"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_max_iterations_trips_to_the_exit_port(monkeypatch):
    """review의 maxRetries=10보다 가드의 maxIterations=2가 먼저 트립돼 exit로 빠진다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", _always_unmet)
    emitter = ListEventEmitter()

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxIterations": 2}), DEFAULT_MODEL_CFG, emitter, "run-1"
    )
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-iter"}},
    )

    assert final["answer"] == "4"
    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2, 3]
    # 가드 노드가 실제 캔버스 노드이므로 nodeId == loopNodeId (설계 §8).
    assert {e.loop_runtime["loopNodeId"] for e in guard_events} == {"guard"}
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"
    assert guard_events[-1].loop_runtime["maxIterations"] == 2


async def test_loop_guard_on_exhaustion_fail_raises_at_runtime(monkeypatch):
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", _always_unmet)

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxIterations": 1, "onExhaustion": "fail"}),
        DEFAULT_MODEL_CFG,
        ListEventEmitter(),
        "run-1",
    )
    with pytest.raises(RuntimeError, match="onExhaustion='fail'"):
        await graph.ainvoke(
            initial_state("", criteria=_ONE_CRITERION, intent="정확한 계산"),
            {"configurable": {"thread_id": "t-loop-fail"}},
        )


async def test_loop_guard_max_tokens_trips_using_derived_members(monkeypatch):
    """reasoning/review가 루프 멤버로 유도돼 토큰을 loop_runtime['guard']에 누적한다."""
    _patch_model(monkeypatch)

    async def reasoning_with_usage(state, *, node_id, usage_sink=None, **kwargs):
        if usage_sink is not None:
            usage_sink["prompt"] = 400
            usage_sink["completion"] = 200
            usage_sink["cost"] = 0.02
        return {"answer": "4", "confidence": 0.9}

    monkeypatch.setattr(compile_mod, "run_llm_step", reasoning_with_usage)
    monkeypatch.setattr(review_mod, "run_llm_step", _always_unmet)
    emitter = ListEventEmitter()

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxTokens": 1000}), DEFAULT_MODEL_CFG, emitter, "run-1"
    )
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-tokens"}},
    )

    assert final["answer"] == "4"
    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert guard_events[-1].loop_runtime["exitReason"] == "budget"
    assert guard_events[-1].loop_runtime["tokens"] >= 1000


async def test_loop_guard_stuck_trips_from_review_progress_history(monkeypatch):
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    async def review_always_two_unmet(state, *, node_id, **kwargs):
        return _delta(
            [
                {"id": "c1", "verdict": "unmet", "evidence": "부족"},
                {"id": "c2", "verdict": "unmet", "evidence": "부족"},
            ]
        )

    monkeypatch.setattr(review_mod, "run_llm_step", review_always_two_unmet)
    emitter = ListEventEmitter()

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"stuckWindow": 2, "stuckThreshold": 1}),
        DEFAULT_MODEL_CFG,
        emitter,
        "run-1",
    )
    criteria = [
        {"id": "c1", "text": "정답 포함", "severity": "must_pass"},
        {"id": "c2", "text": "풀이 포함", "severity": "must_pass"},
    ]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-stuck"}},
    )

    assert final["answer"] == "4"
    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert guard_events[-1].loop_runtime["exitReason"] == "stuck"


async def test_loop_guard_is_reached_from_human_checkpoint_dynamic_goto(monkeypatch):
    """human.checkpoint는 엣지 배선 루프에서 완전히 스킵되고 Command(goto=...)로만
    분기한다 — 가드 노드가 정적 엣지도 선언된 branch mapping도 없이 오직 동적 goto로
    도달된다는 사실을 실제 interrupt/resume 사이클로 증명해 둔다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("checkpoint", "human.checkpoint"),
            _node("guard", "loop.guard", {"maxIterations": 1, "onExhaustion": "exit"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "checkpoint", "answer", "review"),
            _edge("checkpoint", "guard", "revise", "in"),
            _edge("checkpoint", "output", "approve", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    config = {"configurable": {"thread_id": "t-loop-checkpoint"}}

    first = await graph.ainvoke(initial_state(""), config)
    assert first.get("__interrupt__")

    second = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert second.get("__interrupt__")

    final = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert not final.get("__interrupt__")
    assert final["answer"] == "4"

    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2]
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"
```

- [ ] **Step 3: Run them to see them fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k loop_guard -q
```
Expected: 8 failures, mostly `ValueError: Unsupported node type in compiler: 'loop.guard'`.

- [ ] **Step 4: Delete `_prepare_loop_policies`**

In `server/graphs/compile.py`, delete the entire function `_prepare_loop_policies` (lines 285-367, from the `def` line through `return edge_target_override, guard_specs, node_to_policies`).

- [ ] **Step 5: Add `_handle_targets` and clarify the guard's failure message**

Insert immediately above `_tarjan_scc`:

```python
def _handle_targets(outgoing: dict[str, list[dict]], node_id: str) -> dict[str, str]:
    """노드의 outgoing 엣지를 sourceHandle → target 으로 인덱싱한다."""
    return {e["sourceHandle"]: e["target"] for e in outgoing.get(node_id, [])}
```

In `_make_loop_guard_node`, change the `RuntimeError` message (currently lines 409-412) to:

```python
            raise RuntimeError(
                f"loop.guard node {policy_id!r} exhausted ({result['exit_reason']}) "
                "with onExhaustion='fail'"
            )
```

Everything else in `_make_loop_guard_node` stays exactly as-is — the guard evaluation call, the `Command` returns, and the event payload are unchanged (spec §3b).

- [ ] **Step 6: Rewrite `compile_graph`**

Replace the body of `compile_graph` (lines 418-531 after the earlier deletions) with:

```python
def compile_graph(architecture: dict, default_model_cfg: dict, emit: EventEmitter, run_id: str):
    nodes: list[dict] = architecture.get("nodes") or []
    raw_edges: list[dict] = architecture.get("edges") or []

    if not nodes:
        raise ValueError("Architecture has no nodes")

    edges = _filter_control_edges(nodes, raw_edges)

    outgoing: dict[str, list[dict]] = {}
    incoming: dict[str, list[dict]] = {}
    for e in edges:
        outgoing.setdefault(e["source"], []).append(e)
        incoming.setdefault(e["target"], []).append(e)

    loop_node_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}

    # 토큰/비용 예산을 귀속시킬 루프 본체를 그래프에서 유도한다 (설계 §3d).
    # 파라미터 이름 loop_policy_ids는 review/llm_step 쪽 무변경을 위해 유지된다.
    node_to_policies: dict[str, list[str]] = {}
    for loop_node_id in sorted(loop_node_ids):
        continue_target = _handle_targets(outgoing, loop_node_id).get("loopBack")
        for member_id in sorted(_derive_loop_members(loop_node_id, continue_target, outgoing)):
            node_to_policies.setdefault(member_id, []).append(loop_node_id)

    graph = StateGraph(AgentState)
    route_fns: dict[str, Any] = {}

    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        manifest = MANIFESTS_BY_TYPE.get(node_type)
        if manifest is None:
            raise ValueError(f"Unknown node type: {node_type!r} (node {node_id!r})")

        if node_type in PASSTHROUGH_TYPES:
            graph.add_node(
                node_id,
                _make_passthrough_node(node_id, node_type, node.get("config") or {}, emit, run_id),
            )
        elif manifest.get("runtime") == "llm_step":
            model, policy = _resolve_model(node, default_model_cfg)
            graph.add_node(
                node_id,
                _make_llm_step_node(
                    node, manifest, model, policy, emit, run_id, node_to_policies.get(node_id)
                ),
            )
        elif node_type == "review.intent":
            model, policy = _resolve_model(node, default_model_cfg)
            wired = {e["sourceHandle"] for e in outgoing.get(node_id, [])}
            route_fns[node_id] = make_route_review(wired)
            graph.add_node(
                node_id,
                _make_review_node(node, model, policy, emit, run_id, node_to_policies.get(node_id)),
            )
        elif node_type == "human.checkpoint":
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update(_handle_targets(outgoing, node_id))
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
        elif node_type == "loop.guard":
            loop_policy = _loop_policy_from_config(node)
            targets = _handle_targets(outgoing, node_id)
            continue_target = targets.get("loopBack")
            exit_target = targets.get("exit")
            on_exhaustion = loop_policy["onExhaustion"]

            if continue_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} has no 'loopBack' edge — "
                    "wire the Loop back port to the node the loop re-enters"
                )
            if on_exhaustion not in ("exit", "escalate", "fail"):
                raise ValueError(
                    f"loop.guard node {node_id!r} has invalid onExhaustion "
                    f"{on_exhaustion!r} (must be 'exit', 'escalate', or 'fail')"
                )
            if on_exhaustion in ("exit", "escalate") and exit_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} onExhaustion={on_exhaustion!r} "
                    "requires a wired 'exit' port"
                )

            graph.add_node(
                node_id,
                _make_loop_guard_node(
                    loop_policy,
                    node_id,
                    continue_target=continue_target,
                    exit_target=exit_target,
                    emit=emit,
                    run_id=run_id,
                ),
            )
        else:
            raise ValueError(f"Unsupported node type in compiler: {node_type!r}")

    added_plain_edges: set[tuple[str, str]] = set()
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        outs = outgoing.get(node_id, [])

        if node_type == "review.intent":
            graph.add_conditional_edges(node_id, route_fns[node_id], _handle_targets(outgoing, node_id))
            continue
        # human.checkpoint / loop.guard는 Command(goto=...)로 스스로 라우팅하므로
        # plain edge를 추가하지 않는다.
        if node_type in ("human.checkpoint", "loop.guard"):
            continue

        if not outs:
            graph.add_edge(node_id, END)
            continue
        for e in outs:
            pair = (node_id, e["target"])
            if pair in added_plain_edges:
                continue
            added_plain_edges.add(pair)
            graph.add_edge(node_id, e["target"])

    entry_ids = [n["id"] for n in nodes if not incoming.get(n["id"])]
    if not entry_ids:
        raise ValueError("Architecture has no entry node (a node with no incoming edges)")
    for eid in entry_ids:
        graph.add_edge(START, eid)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
```

Note what disappeared: the `nodes_by_id` / `edges_by_id` maps, the `loop_policies` read, the `_prepare_loop_policies` call, the pre-loop `guard_specs` registration block, and every `edge_target_override.get(...)` lookup.

- [ ] **Step 7: Run the new tests to verify they pass**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k loop_guard -q
```
Expected: 8 passed.

- [ ] **Step 8: Run the whole backend suite — `test_loop_guard.py` must pass untouched**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest -q
git -C /home/licodev/projects/agentforge diff --stat -- server/nodes/loop_guard.py server/tests/test_loop_guard.py server/state.py server/nodes/review.py server/nodes/llm_step.py
```
Expected: `test_compile.py`'s two remaining cycle tests (`test_compile_no_entry_raises`, `test_review_refine_loop_then_accept`, `test_architecture_without_loop_policies_key_behaves_unchanged`) still pass because validation isn't wired yet; everything else passes. The `git diff --stat` prints **nothing** — proof the frozen files are untouched (spec §10 "무변경(재사용)").

- [ ] **Step 9: Lint and format**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/python -m pytest -q
```
Expected: clean, all green.

- [ ] **Step 10: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_compile.py && git commit -m "feat(server): compile loop.guard as a first-class node, drop the LoopPolicy sidecar"
```

---

### Task 7: Enable ungated-cycle validation (intended breaking change)

**Files:**
- Modify: `server/graphs/compile.py` (one call inside `compile_graph`)
- Test: `server/tests/test_compile.py:81-89` (rewrite), `:191-229` (rewrite), `:677-720` (delete), plus 2 new tests

**Interfaces:**
- Consumes: `_validate_gated_cycles` (Task 5), the compiler wiring (Task 6).
- Produces: `compile_graph` raises `ValueError("Cycle without a loop.guard node: [...]")` for any SCC of size ≥ 2 with no `loop.guard` member, before any node is registered.

- [ ] **Step 1: Write the failing compile-level cycle tests**

Append to `server/tests/test_compile.py`:

```python
async def test_cycle_without_loop_guard_raises(monkeypatch):
    """review --refine--> reasoning 직결 루프는 이제 컴파일 에러다 (설계 §4, 의도된
    breaking change — Loop 노드를 끼워야 컴파일된다)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "reasoning", "refine", "task"),
            _edge("review", "output", "accept", "result"),
        ],
    )
    with pytest.raises(ValueError, match="Cycle without a loop.guard node"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_cycle_with_loop_guard_compiles(monkeypatch):
    _patch_model(monkeypatch)
    graph = compile_mod.compile_graph(
        _gated_refine_arch({}), DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1"
    )
    assert graph is not None
```

- [ ] **Step 2: Run them to see the first one fail**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -k "cycle_with" -q
```
Expected: `test_cycle_without_loop_guard_raises` FAILS (`DID NOT RAISE`); `test_cycle_with_loop_guard_compiles` passes.

- [ ] **Step 3: Wire the validator into `compile_graph`**

In `server/graphs/compile.py`, inside `compile_graph`, add one line immediately after `loop_node_ids = {...}`:

```python
    loop_node_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}
    _validate_gated_cycles([n["id"] for n in nodes], edges, loop_node_ids)
```

- [ ] **Step 4: Run the whole backend suite to see exactly which existing tests the breaking change breaks**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_compile.py -q
```
Expected: 3 failures — `test_compile_no_entry_raises`, `test_review_refine_loop_then_accept`, `test_architecture_without_loop_policies_key_behaves_unchanged`. Nothing else. If anything else fails, stop and investigate before continuing.

- [ ] **Step 5: Rewrite `test_compile_no_entry_raises` to use a gated cycle**

Replace it (lines 81-89) with:

```python
async def test_compile_no_entry_raises(monkeypatch):
    """모든 노드에 incoming이 있으면(순환) 진입점 부재 ValueError.

    cycle 검증이 먼저 돌기 때문에 가드가 포함된 루프여야 이 에러까지 도달한다."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("a", "reasoning.cot"),
            _node("g", "loop.guard", {"onExhaustion": "fail"}),
        ],
        [_edge("a", "g", "answer", "in"), _edge("g", "a", "loopBack", "task")],
    )
    with pytest.raises(ValueError, match="no entry"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
```

- [ ] **Step 6: Rewrite `test_review_refine_loop_then_accept` to route refine through a guard**

Replace it (lines 191-229) with:

```python
async def test_review_refine_loop_then_accept(monkeypatch):
    """review의 refine 핸들→guard→reasoning 루프 후 accept 핸들→output.

    가드 축을 하나도 설정하지 않았으므로 판정은 8/6 이전과 동일해야 한다 —
    가드 도입이 기존 review 3분기 동작을 바꾸지 않는다는 회귀 증거."""
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
    graph = compile_mod.compile_graph(
        _gated_refine_arch({}, review_config={}), DEFAULT_MODEL_CFG, emitter, "run-1"
    )
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="정확한 계산"),
        {"configurable": {"thread_id": "t3"}},
    )

    assert final["review_branch"] == "accept"
    assert final["retries"] == 1
    branches = [e.policy_decision["branch"] for e in emitter.events if e.policy_decision]
    assert branches == ["refine", "accept"]

    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1]
    assert "exitReason" not in guard_events[0].loop_runtime
```

- [ ] **Step 7: Delete the obsolete migration test**

Delete `test_architecture_without_loop_policies_key_behaves_unchanged` (lines 677-720) in its entirety. Its premise — an Architecture with no `loopPolicies` key — stops existing once the key does. Its regression value now lives in `test_review_refine_loop_then_accept` (same accept/refine/retries outcome through a gated loop) and `test_cycle_without_loop_guard_raises` (the intended breaking change).

- [ ] **Step 8: Run the whole backend suite to verify it is green**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format . && .venv/bin/python -m pytest -q
```
Expected: 0 failures.

- [ ] **Step 9: Prove it actually runs — compile and execute a gated loop outside pytest**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -c "
import asyncio
from events import ListEventEmitter
from state import initial_state
from graphs.compile import compile_graph

arch = {'version':'1','metadata':{'name':'smoke'},'nodes':[
  {'id':'input','type':'io.input','position':{'x':0,'y':0},'config':{'sample':'2+2'}},
  {'id':'reasoning','type':'reasoning.cot','position':{'x':0,'y':0},'config':{}},
  {'id':'review','type':'review.intent','position':{'x':0,'y':0},'config':{}},
  {'id':'guard','type':'loop.guard','position':{'x':0,'y':0},'config':{'maxIterations':2,'onExhaustion':'exit'}},
  {'id':'output','type':'io.output','position':{'x':0,'y':0},'config':{}}],
 'edges':[
  {'id':'a','source':'input','sourceHandle':'task','target':'reasoning','targetHandle':'task'},
  {'id':'b','source':'reasoning','sourceHandle':'answer','target':'review','targetHandle':'answer'},
  {'id':'c','source':'review','sourceHandle':'refine','target':'guard','targetHandle':'in'},
  {'id':'d','source':'review','sourceHandle':'accept','target':'output','targetHandle':'result'},
  {'id':'e','source':'guard','sourceHandle':'loopBack','target':'reasoning','targetHandle':'task'},
  {'id':'f','source':'guard','sourceHandle':'exit','target':'output','targetHandle':'result'}]}

print('gated graph compiled:', compile_graph(arch, {'provider':'google','model':'gemini-3.1-flash-lite','temperature':0}, ListEventEmitter(), 'r') is not None)

del arch['nodes'][3]
arch['edges'] = [e for e in arch['edges'] if e['id'] not in ('c','e','f')]
arch['edges'].append({'id':'g','source':'review','sourceHandle':'refine','target':'reasoning','targetHandle':'task'})
try:
    compile_graph(arch, {'provider':'google','model':'gemini-3.1-flash-lite','temperature':0}, ListEventEmitter(), 'r')
    raise SystemExit('FAIL: ungated cycle compiled')
except ValueError as exc:
    print('ungated cycle rejected:', exc)
"
```
Expected output:
```
gated graph compiled: True
ungated cycle rejected: Cycle without a loop.guard node: ['reasoning', 'review'] — add a Loop node on the feedback edge
```

- [ ] **Step 10: Commit**

```bash
cd /home/licodev/projects/agentforge && git add server/graphs/compile.py server/tests/test_compile.py && git commit -m "feat(server): reject cycles drawn without a loop.guard node"
```

---

### Task 8: Delete the frontend `LoopPolicy` sidecar schema and store state

**Files:**
- Modify: `ui/src/types/graph.ts:29-72`
- Modify: `ui/src/stores/useGraphStore.ts:12, 31, 61, 138, 145, 162`
- Modify: `ui/src/app/starterArchitecture.ts:35`
- Delete: `ui/src/__tests__/loopPolicy.schema.test.ts`
- Modify: `ui/src/__tests__/graphStore.test.ts:35-45, 65-69`

**Interfaces:**
- Produces: `ArchitectureSchema` with exactly `version`, `metadata`, `nodes`, `edges`. `LOOP_POLICY_KINDS` and `LOOP_POLICY_EXHAUSTION_ACTIONS` stay exported (Task 1's manifest consumes them).
- Consumes: nothing.

- [ ] **Step 1: Delete the sidecar-only test file and the store round-trip assertions**

```bash
cd /home/licodev/projects/agentforge && git rm ui/src/__tests__/loopPolicy.schema.test.ts
```

In `ui/src/__tests__/graphStore.test.ts`, delete the `loopPolicies: [...]` block from the `architecture` fixture (lines 35-45, i.e. the whole property including the trailing comma) and delete the `'preserves loop policies through load and serialize'` test (lines 65-69).

- [ ] **Step 2: Run the suite to see the remaining sidecar references fail to type-check/run**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- graphStore && npm run build
```
Expected: the vitest run passes but `npm run build` FAILS with `Property 'loopPolicies' is missing in type ... but required in type 'Architecture'` at `ui/src/__tests__/graphStore.test.ts`. That failure is the driver for Step 3.

- [ ] **Step 3: Remove the schema**

In `ui/src/types/graph.ts`, delete lines 29-60 (`LoopPolicyGuardSchema`, `LoopPolicyGuard`, `LoopPolicySchema`, `LoopPolicy`) **except** the two const arrays, and drop the `loopPolicies` field. The file's tail becomes:

```ts
/**
 * Loop 노드(`loop.guard`) manifest의 `kind` / `onExhaustion` select 옵션 소스.
 * guard 모양과는 무관한 순수 문자열 목록이다 — 노드 config 자체는 다른 노드 타입과
 * 마찬가지로 `GraphNodeSchema.config`(타입 검증 없는 record)에 담긴다.
 * See docs/superpowers/specs/2026-08-07-loop-node-design.md §2.
 */
export const LOOP_POLICY_KINDS = ['evaluatorOptimizer', 'critiqueRevise', 'humanReview'] as const
export const LOOP_POLICY_EXHAUSTION_ACTIONS = ['exit', 'escalate', 'fail'] as const

export const ArchitectureSchema = z.object({
  version: z.string().default('0.1'),
  metadata: z.object({
    name: z.string(),
    description: z.string().optional(),
    createdAt: z.string(),
  }),
  nodes: z.array(GraphNodeSchema).default([]),
  edges: z.array(GraphEdgeSchema).default([]),
})
export type Architecture = z.infer<typeof ArchitectureSchema>
```

- [ ] **Step 4: Remove the store state**

In `ui/src/stores/useGraphStore.ts`:
- line 12 → `import type { Architecture, GraphNode } from '@/types'`
- delete line 31 (`loopPolicies: LoopPolicy[]`)
- delete line 61 (`loopPolicies: [],`)
- delete line 138 (`loopPolicies: arch.loopPolicies,`)
- line 145 → `const { nodes, edges } = get()`
- delete line 162 (`loopPolicies,`)

- [ ] **Step 5: Remove `loopPolicies` from the starter architecture**

In `ui/src/app/starterArchitecture.ts`, delete line 35 (`  loopPolicies: [],`).

- [ ] **Step 6: Run the frontend gates**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test && npm run lint && npm run build
```
Expected: all tests pass, lint clean, `tsc -b` + Vite build succeed. If `build` reports `'LoopPolicy' is declared but never used` anywhere, delete that import too.

- [ ] **Step 7: Confirm nothing references the deleted schema**

```bash
cd /home/licodev/projects/agentforge/ui/src && grep -rn "LoopPolicySchema\|LoopPolicyGuard\|loopPolicies" --include="*.ts" --include="*.tsx" .
```
Expected: no output.

- [ ] **Step 8: Commit**

```bash
cd /home/licodev/projects/agentforge && git add -A ui/src && git commit -m "refactor(ui): remove the LoopPolicy sidecar schema and store state"
```

---

### Task 9: Delete the Loop Scope Lens and the orphaned loop UI

~1,790 lines across 13 source files and 8 test files, plus the three live call sites.

**Files:**
- Delete: `ui/src/canvas/loops/{loopAnchors,loopCandidates,loopEdgeAnnotations,loopScopeBoundaryPorts,loopScopeInspector,loopScopeProjection,loopScopes,tier3LoopLane}.ts` (the whole directory)
- Delete: `ui/src/canvas/nodes/LoopScopeNode.tsx`, `ui/src/canvas/nodes/LoopAnchor.tsx`, `ui/src/canvas/LoopControlPanel.tsx`
- Delete: `ui/src/panels/LoopScopeInspector.tsx`, `ui/src/panels/LoopCandidateInspector.tsx`
- Delete: `ui/src/__tests__/{loopAnchors,loopCandidates,loopEdgeAnnotations,loopScopeBoundaryPorts,loopScopeInspector,loopScopeProjection,loopScopes,tier3LoopLane}.test.ts`
- Modify: `ui/src/canvas/Canvas.tsx:25-34, 102-142, 175, 233-240`
- Modify: `ui/src/panels/Inspector.tsx:10-11, 27-29, 38-40`
- Modify: `ui/src/canvas/nodes/AgentNode.tsx:6-7, 10-11, 14-19, 25-26, 28, 46-48, 58-62, 90-97`
- Modify: `ui/src/stores/useUiStore.ts`
- Modify: `ui/src/__tests__/uiStore.test.ts:37-83`

**Interfaces:**
- Consumes: nothing.
- Produces: `useUiStore`'s `UiState` reduced to `panels`, `canvasNodeMode`, `showConnectionPorts`, `togglePanel`, `setCanvasNodeMode`, `toggleConnectionPorts`. No other module may reference the removed members.

- [ ] **Step 1: Delete the orphaned files and their tests**

```bash
cd /home/licodev/projects/agentforge && git rm -r ui/src/canvas/loops \
  ui/src/canvas/nodes/LoopScopeNode.tsx \
  ui/src/canvas/nodes/LoopAnchor.tsx \
  ui/src/canvas/LoopControlPanel.tsx \
  ui/src/panels/LoopScopeInspector.tsx \
  ui/src/panels/LoopCandidateInspector.tsx \
  ui/src/__tests__/loopAnchors.test.ts \
  ui/src/__tests__/loopCandidates.test.ts \
  ui/src/__tests__/loopEdgeAnnotations.test.ts \
  ui/src/__tests__/loopScopeBoundaryPorts.test.ts \
  ui/src/__tests__/loopScopeInspector.test.ts \
  ui/src/__tests__/loopScopeProjection.test.ts \
  ui/src/__tests__/loopScopes.test.ts \
  ui/src/__tests__/tier3LoopLane.test.ts
```

- [ ] **Step 2: Run the build to enumerate every broken import**

```bash
cd /home/licodev/projects/agentforge/ui && npm run build
```
Expected: `tsc -b` errors in exactly three files — `canvas/Canvas.tsx`, `panels/Inspector.tsx`, `canvas/nodes/AgentNode.tsx`. That list is your worklist for Steps 3-5.

- [ ] **Step 3: Clean up `Canvas.tsx`**

Delete these imports (lines 25-32): `import { LoopControlPanel } from './LoopControlPanel'`, the whole `import { buildLoopAnchorsByNodeId, buildLoopCandidateViews, candidateReturnEdgeIds, type LoopAnchor } from './loops/loopAnchors'` block, and `import type { RFNodeData } from '@/stores/useGraphStore'` (it existed only for the type on line 34). Delete the `type LoopAnnotatedNodeData = ...` line (34).

Replace the five `useMemo` blocks at lines 102-142 with just:

```tsx
  const renderedEdges = useMemo(
    () =>
      canvasNodeMode === 'agent'
        ? edges.map((edge) => ({ ...edge, type: 'agent' }))
        : edges,
    [canvasNodeMode, edges],
  )
```

Change line 175 from `nodes={displayNodes}` to `nodes={nodes}`.

Delete the `LoopControlPanel` render block (lines 233-240):

```tsx
          {canvasNodeMode === 'agent' && (
            <LoopControlPanel
              candidates={loopCandidates}
              selectedCandidateId={selectedNodeId?.startsWith('loop:') ? selectedNodeId : null}
              labelByNodeId={labelByNodeId}
              onSelect={select}
            />
          )}
```

`selectedNodeId` stays — `arrangeRadially` still uses it.

- [ ] **Step 4: Clean up `Inspector.tsx`**

Delete the two imports at lines 10-11 (`buildLoopCandidateViews`, `LoopCandidateInspector`), the `selectedLoopCandidate` const (lines 27-29), and the early-return block (lines 38-40):

```tsx
  if (selectedLoopCandidate) {
    return <LoopCandidateInspector candidate={selectedLoopCandidate} nodes={allNodes} edges={edges} />
  }
```

`allNodes` and `edges` stay — the Connections section still reads them.

- [ ] **Step 5: Clean up `AgentNode.tsx`**

Delete: line 6 (`import { useGraphStore }`), line 7 (`import { useUiStore }`), lines 10-11 (`LoopAnchorData`, `LoopAnchor`), lines 14-19 (the `LoopAnnotatedData` type + its comment), line 25 (`selectedNodeId`), line 26 (`hoveredLoopCandidateId`), line 28 (`const { loopAnchors = [] } = ...`), lines 46-48 (`highlightedLoop`), and lines 90-97 (the `loopAnchors.map(...)` render).

Replace the `boxShadow` expression (lines 55-62) with:

```tsx
        boxShadow:
          status === 'running'
            ? `0 0 0 1px ${meta.color}88, 0 0 18px ${meta.color}44`
            : selected
              ? `0 0 0 1px ${meta.color}66`
              : undefined,
```

- [ ] **Step 6: Strip the dead loop state from `useUiStore`**

Replace `ui/src/stores/useUiStore.ts` in full with:

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
  togglePanel: (key: keyof UiState['panels']) => void
  setCanvasNodeMode: (mode: CanvasNodeMode) => void
  toggleConnectionPorts: () => void
}

export const useUiStore = create<UiState>((set) => ({
  panels: { library: true, inspector: true, log: true },
  canvasNodeMode: 'agent',
  showConnectionPorts: false,
  togglePanel: (key) =>
    set((s) => ({ panels: { ...s.panels, [key]: !s.panels[key] } })),
  setCanvasNodeMode: (canvasNodeMode) => set({ canvasNodeMode }),
  toggleConnectionPorts: () => set((s) => ({ showConnectionPorts: !s.showConnectionPorts })),
}))
```

In `ui/src/__tests__/uiStore.test.ts`, delete the two trailing `describe` blocks — `'useUiStore loop scope expansion'` (lines 37-64) and `'useUiStore raw execution view'` (lines 66-83). The two remaining blocks stay untouched.

- [ ] **Step 7: Run the frontend gates**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test && npm run lint && npm run build
```
Expected: all tests pass; lint clean; `tsc -b` + Vite build succeed with no unused-import or unused-variable errors.

- [ ] **Step 8: Confirm nothing references the Lens any more**

```bash
cd /home/licodev/projects/agentforge/ui/src && grep -rn "LoopScope\|loopScope\|LoopAnchor\|loopAnchor\|LoopCandidate\|loopCandidate\|LoopControlPanel\|tier3LoopLane\|loopEdgeAnnotations\|rawExecutionView" --include="*.ts" --include="*.tsx" . ; ls canvas/loops 2>&1
```
Expected: `grep` prints nothing; `ls` prints `No such file or directory`.

- [ ] **Step 9: Prove it actually runs — the app boots and the canvas renders**

```bash
cd /home/licodev/projects/agentforge/ui && timeout 40 npx vite preview --port 5199 --strictPort >/tmp/vite-preview.log 2>&1 &
sleep 5 && curl -sf http://localhost:5199/ | head -20 && kill %1
```
Expected: the built `index.html` is served (Vite preview needs the `dist/` produced by Step 7's `npm run build`). Then open `http://localhost:5137` via `./start.sh` and confirm visually that the canvas renders in both `classic` and `agent` modes with the top-right panel showing only the mode switch and the 연결 편집모드 toggle — no Loop panel.

- [ ] **Step 10: Commit**

```bash
cd /home/licodev/projects/agentforge && git add -A ui/src && git commit -m "refactor(ui): delete the Loop Scope Lens and its orphaned canvas code"
```

---

### Task 10: Put a `loop.guard` node into the starter architecture

The starter graph's `Reasoning → Review → (refine) → Reasoning` cycle is now a compile error without a guard, so this is required — and it makes the new feature demo itself on first load.

**Files:**
- Modify: `ui/src/app/starterArchitecture.ts`
- Test: `ui/src/__tests__/starterArchitecture.test.ts` (create)

**Interfaces:**
- Consumes: the `loop.guard` manifest port ids (Task 1), the slimmed `ArchitectureSchema` (Task 8).
- Produces: node id `'loop_guard'` and edge ids `'e9'` (loopBack → reasoning) / `'e10'` (exit → output). Task 11's backend integration test mirrors this graph exactly.

- [ ] **Step 1: Write the failing starter-graph test**

Create `ui/src/__tests__/starterArchitecture.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { ArchitectureSchema } from '@/types'
import { STARTER_ARCHITECTURE } from '@/app/starterArchitecture'

const guard = () => STARTER_ARCHITECTURE.nodes.find((n) => n.type === 'loop.guard')

describe('STARTER_ARCHITECTURE', () => {
  it('ArchitectureSchema를 통과한다', () => {
    expect(() => ArchitectureSchema.parse(STARTER_ARCHITECTURE)).not.toThrow()
  })

  it('refine 피드백이 loop.guard 노드로 들어간다', () => {
    const refine = STARTER_ARCHITECTURE.edges.find((e) => e.sourceHandle === 'refine')
    expect(guard()).toBeDefined()
    expect(refine?.target).toBe(guard()!.id)
    expect(refine?.targetHandle).toBe('in')
  })

  it('loop.guard의 loopBack/exit 포트가 모두 배선돼 있다', () => {
    // 백엔드 compile_graph는 둘 중 하나라도 비면 ValueError를 던진다.
    const handles = STARTER_ARCHITECTURE.edges
      .filter((e) => e.source === guard()!.id)
      .map((e) => e.sourceHandle)
      .sort()
    expect(handles).toEqual(['exit', 'loopBack'])
  })

  it('reasoning으로 되돌아오는 유일한 피드백 경로가 loop.guard를 거친다', () => {
    // 가드를 우회하는 되돌림 엣지가 하나라도 있으면 ungated cycle 컴파일 에러가 난다.
    const feedbackIntoReasoning = STARTER_ARCHITECTURE.edges
      .filter((e) => e.target === 'reasoning' && !['input', 'planning'].includes(e.source))
      .map((e) => e.source)
    expect(feedbackIntoReasoning).toEqual([guard()!.id])
  })

  it('가드에 유한한 maxIterations와 exit 소진 정책이 설정돼 있다', () => {
    expect(guard()!.config.maxIterations).toBe(3)
    expect(guard()!.config.onExhaustion).toBe('exit')
  })
})
```

- [ ] **Step 2: Run it to see it fail**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- starterArchitecture
```
Expected: 4 failures — `guard()` is `undefined`.

- [ ] **Step 3: Add the `loop.guard` node and rewire the refine edge**

In `ui/src/app/starterArchitecture.ts`, update the doc comment, insert the guard node after `review`, and change `e6` / add `e9`, `e10`:

```ts
/**
 * 스타터 그래프: 의도 정합성 리뷰 흐름 (POLICY_REDESIGN.md Phase 1).
 * Input → Planning → Reasoning → Review (intent×criteria diff)
 *   ├ accept  → Output
 *   ├ refine  → Loop (loop.guard) ─ loop back → Reasoning (재작업)
 *   │                             └ exit      → Output (가드 소진 시)
 *   └ clarify → Human Checkpoint → Output
 *
 * refine 피드백이 Loop 노드를 거치는 것은 선택이 아니다 — 가드 없이 그려진 cycle은
 * compile_graph가 ValueError로 거부한다.
 * See docs/superpowers/specs/2026-08-07-loop-node-design.md §4.
 */
```

```ts
    { id: 'review',            type: 'review.intent',       position: { x: 690, y: 300 }, config: { criteria: [], maxRetries: 2, modelSlots: [{ id: 'slot-review', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'loop_guard',        type: 'loop.guard',          position: { x: 916, y: 430 }, config: { kind: 'critiqueRevise', maxIterations: 3, onExhaustion: 'exit' } },
    { id: 'human_checkpoint',  type: 'human.checkpoint',    position: { x: 748, y: 520 }, config: {} },
```

```ts
    { id: 'e6',  source: 'review',           sourceHandle: 'refine',   target: 'loop_guard',       targetHandle: 'in'     },
    { id: 'e7',  source: 'review',           sourceHandle: 'clarify',  target: 'human_checkpoint', targetHandle: 'review' },
    { id: 'e8',  source: 'human_checkpoint', sourceHandle: 'approve',  target: 'output',           targetHandle: 'result' },
    { id: 'e9',  source: 'loop_guard',       sourceHandle: 'loopBack', target: 'reasoning',        targetHandle: 'task'   },
    { id: 'e10', source: 'loop_guard',       sourceHandle: 'exit',     target: 'output',           targetHandle: 'result' },
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test -- starterArchitecture
```
Expected: 5 passed.

- [ ] **Step 5: Verify the starter graph actually compiles on the backend**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -c "
import json, re, pathlib
src = pathlib.Path('../ui/src/app/starterArchitecture.ts').read_text(encoding='utf-8')
guard_ids = re.findall(r\"id: '(\w+)',\s+type: 'loop\.guard'\", src)
print('loop.guard nodes in starter:', guard_ids)
assert guard_ids == ['loop_guard']
for handle in ('loopBack', 'exit'):
    assert f\"sourceHandle: '{handle}'\" in src, handle
print('loopBack/exit both wired in starterArchitecture.ts')
"
```
Expected: prints `['loop_guard']` and the confirmation line. (Task 11's `test_ws_starter_graph.py` does the real compile-and-run.)

- [ ] **Step 6: Run the full frontend gates**

```bash
cd /home/licodev/projects/agentforge/ui && npm run test && npm run lint && npm run build
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
cd /home/licodev/projects/agentforge && git add ui/src/app/starterArchitecture.ts ui/src/__tests__/starterArchitecture.test.ts && git commit -m "feat(ui): gate the starter graph's refine loop with a loop.guard node"
```

---

### Task 11: End-to-end verification — the step the 8/6 implementation skipped

This task adds one permanent integration test and then runs everything for real: the full suites, a live GSM8K benchmark against Gemini, and a live WebSocket execution of the starter graph through `ws_run → dispatch_graph → compile_graph`.

**Files:**
- Test: `server/tests/test_ws_starter_graph.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1-10.
- Produces: `STARTER_ARCHITECTURE` (a Python dict mirroring `ui/src/app/starterArchitecture.ts`) used by the integration test.

- [ ] **Step 1: Write the failing WebSocket integration test**

Create `server/tests/test_ws_starter_graph.py`:

```python
"""ws_run → dispatch_graph → compile_graph 전체 경로를, loop.guard가 들어간 스타터
그래프 그대로 통과시키는 통합 테스트. LLM은 목(AGENTS.md §6).

단위 테스트만 통과하고 실제로는 한 번도 실행되지 않은 채 머지된 8/6 사고를 막는
장치다 — 여기가 깨지면 브라우저에서 Run 버튼을 눌렀을 때 깨진다는 뜻이다.
아키텍처 모양은 ui/src/app/starterArchitecture.ts와 1:1로 유지한다.
"""

import graphs.compile as compile_mod
import nodes.review as review_mod
import workspace as workspace_mod
from fastapi.testclient import TestClient

STARTER_ARCHITECTURE = {
    "version": "0.1",
    "metadata": {"name": "GSM8K Treatment (starter)", "createdAt": "2026-08-07T00:00:00.000Z"},
    "nodes": [
        {"id": "input", "type": "io.input", "position": {"x": 96, "y": 88}, "config": {"sample": "2+2"}},
        {"id": "planning", "type": "planning.decompose", "position": {"x": 272, "y": 220}, "config": {}},
        {"id": "reasoning", "type": "reasoning.cot", "position": {"x": 472, "y": 356}, "config": {}},
        {"id": "review", "type": "review.intent", "position": {"x": 690, "y": 300}, "config": {"criteria": [], "maxRetries": 2}},
        {"id": "loop_guard", "type": "loop.guard", "position": {"x": 916, "y": 430}, "config": {"kind": "critiqueRevise", "maxIterations": 3, "onExhaustion": "exit"}},
        {"id": "human_checkpoint", "type": "human.checkpoint", "position": {"x": 748, "y": 520}, "config": {}},
        {"id": "output", "type": "io.output", "position": {"x": 522, "y": 616}, "config": {}},
    ],
    "edges": [
        {"id": "e1", "source": "input", "sourceHandle": "task", "target": "planning", "targetHandle": "task"},
        {"id": "e2", "source": "planning", "sourceHandle": "plan", "target": "reasoning", "targetHandle": "plan"},
        {"id": "e3", "source": "input", "sourceHandle": "task", "target": "reasoning", "targetHandle": "task"},
        {"id": "e4", "source": "reasoning", "sourceHandle": "answer", "target": "review", "targetHandle": "answer"},
        {"id": "e5", "source": "review", "sourceHandle": "accept", "target": "output", "targetHandle": "result"},
        {"id": "e6", "source": "review", "sourceHandle": "refine", "target": "loop_guard", "targetHandle": "in"},
        {"id": "e7", "source": "review", "sourceHandle": "clarify", "target": "human_checkpoint", "targetHandle": "review"},
        {"id": "e8", "source": "human_checkpoint", "sourceHandle": "approve", "target": "output", "targetHandle": "result"},
        {"id": "e9", "source": "loop_guard", "sourceHandle": "loopBack", "target": "reasoning", "targetHandle": "task"},
        {"id": "e10", "source": "loop_guard", "sourceHandle": "exit", "target": "output", "targetHandle": "result"},
    ],
}


def _delta(per_criterion):
    return {
        "per_criterion": per_criterion,
        "misalignments": [],
        "elicit_questions": [],
        "proposed_criteria": [],
        "reroute_hint": "",
    }


def _drain(ws) -> tuple[list[dict], dict]:
    events: list[dict] = []
    while True:
        msg = ws.receive_json()
        if msg["kind"] == "event":
            events.append(msg["event"])
            continue
        if msg["kind"] == "run_started":
            continue
        return events, msg


def test_starter_graph_runs_end_to_end_over_the_websocket(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    async def fake_llm_step(state, *, node_id, **kwargs):
        if node_id == "planning":
            return {"steps": ["s1"]}
        return {"answer": "4", "confidence": 0.9}

    calls = {"review": 0}

    async def fake_review(state, *, node_id, **kwargs):
        calls["review"] += 1
        verdict = "unmet" if calls["review"] == 1 else "met"
        return _delta([{"id": "c1", "verdict": verdict, "evidence": "ev"}])

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", fake_review)

    from main import app

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        ws.send_json(
            {
                "kind": "run",
                "architecture": STARTER_ARCHITECTURE,
                "input": {
                    "task": "2+2",
                    "criteria": [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}],
                },
                "model": {},
            }
        )
        events, outcome = _drain(ws)

    assert outcome["kind"] == "run_complete", outcome
    assert outcome["result"]["answer"] == "4"
    assert outcome["result"]["reviewBranch"] == "accept"

    guard_events = [e for e in events if e["nodeId"] == "loop_guard" and e.get("loopRuntime")]
    assert guard_events, "loop.guard 노드가 한 번도 실행되지 않았다"
    assert guard_events[0]["loopRuntime"]["loopNodeId"] == "loop_guard"
    assert guard_events[0]["loopRuntime"]["iteration"] == 1
    assert guard_events[0]["loopRuntime"]["maxIterations"] == 3


def test_starter_graph_exits_through_the_guard_when_iterations_run_out(monkeypatch, tmp_path):
    """review가 끝없이 refine을 원해도 maxIterations=3이 exit 포트로 강제 이탈시킨다."""
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    async def fake_llm_step(state, *, node_id, **kwargs):
        if node_id == "planning":
            return {"steps": ["s1"]}
        return {"answer": "4", "confidence": 0.9}

    async def always_unmet(state, *, node_id, **kwargs):
        return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", always_unmet)

    arch = {**STARTER_ARCHITECTURE}
    arch["nodes"] = [
        {**n, "config": {**n["config"], "maxRetries": 10}} if n["id"] == "review" else n
        for n in STARTER_ARCHITECTURE["nodes"]
    ]

    from main import app

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        ws.send_json(
            {
                "kind": "run",
                "architecture": arch,
                "input": {
                    "task": "2+2",
                    "criteria": [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}],
                },
                "model": {},
            }
        )
        events, outcome = _drain(ws)

    assert outcome["kind"] == "run_complete", outcome
    guard_events = [e for e in events if e["nodeId"] == "loop_guard" and e.get("loopRuntime")]
    assert [e["loopRuntime"]["iteration"] for e in guard_events] == [1, 2, 3, 4]
    assert guard_events[-1]["loopRuntime"]["exitReason"] == "maxIterations"
```

- [ ] **Step 2: Run it**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python -m pytest tests/test_ws_starter_graph.py -q
```
Expected: 2 passed. **If either fails, that is the real defect this whole plan exists to catch** — debug with `superpowers:systematic-debugging` before continuing; do not weaken the assertions.

- [ ] **Step 3: Run every backend gate**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q
```
Expected: `ruff` clean, 0 test failures. Confirm the summary line shows `test_loop_guard.py`'s 12 tests among the passes (spec test-plan item 2 — regression evidence from a completely untouched file).

- [ ] **Step 4: Run every frontend gate**

```bash
cd /home/licodev/projects/agentforge/ui && npm run lint && npm run test && npm run build
```
Expected: oxlint clean; all vitest suites pass; `tsc -b` + Vite build succeed (only the pre-existing >500 kB chunk-size warning).

- [ ] **Step 5: Commit the integration test**

```bash
cd /home/licodev/projects/agentforge && git add server/tests/test_ws_starter_graph.py && git commit -m "test(server): run the loop.guard starter graph end-to-end over /ws/run"
```

- [ ] **Step 6: Run the GSM8K benchmark against a live model**

The default model is `gemini-3.1-flash-lite` (Google) — `config.yaml:models.default` and `server/main.py:132`. This uses `GOOGLE_API_KEY` from `server/.env`, **not** Anthropic, so a 401 on the Anthropic key is irrelevant here.

```bash
cd /home/licodev/projects/agentforge/server && ls data/benchmark-*.json && .venv/bin/python scripts/run_benchmark.py --arch both --limit 3 && ls -la data/benchmark-*.json
```
Expected: the table prints for `baseline` and `treatment`, then `결과 저장: data/benchmark-<today>T...Z.json`, and the second `ls` shows a file dated today that the first `ls` did not.

**Scope note to record in the commit/report:** `run_benchmark.py` builds graphs via `graphs/baseline.py` and `graphs/treatment.py`, **not** via `compile_graph` — so this proves the backend still executes against a live model, but it does **not** exercise `loop.guard`. Step 7 is what exercises `loop.guard` live.

**If the Google key is dead:** re-run with `--provider anthropic --model claude-haiku-4-5-20251001`. If both providers fail, record the exact error text in the final report, mark this step BLOCKED (do not mark it done), and rely on Steps 2-4 and 7 for verification.

- [ ] **Step 7: Run the starter graph — with `loop.guard` — live, through the real WebSocket path**

```bash
cd /home/licodev/projects/agentforge/server && .venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from tests.test_ws_starter_graph import STARTER_ARCHITECTURE
from main import app

arch = json.loads(json.dumps(STARTER_ARCHITECTURE))
for node in arch["nodes"]:
    if node["type"] in ("planning.decompose", "reasoning.cot", "review.intent"):
        node["config"]["modelSlots"] = [{
            "id": f"slot-{node['id']}", "provider": "google",
            "model": "gemini-3.1-flash-lite", "temperature": 0, "role": "",
        }]

task = ("Natalia sold clips to 48 of her friends in April, and then she sold half as "
        "many clips in May. How many clips did Natalia sell altogether in April and May?")

with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
    ws.send_json({"kind": "run", "architecture": arch,
                  "input": {"task": task, "criteria": []}, "model": {}})
    guard_hits = 0
    while True:
        msg = ws.receive_json()
        kind = msg["kind"]
        if kind == "event":
            ev = msg["event"]
            if ev.get("loopRuntime"):
                guard_hits += 1
                print("GUARD", ev["nodeId"], ev["loopRuntime"])
            elif ev["eventType"] in ("node_start", "error"):
                print(ev["eventType"], ev["nodeId"], ev.get("error") or "")
            continue
        if kind == "run_started":
            continue
        print(kind, json.dumps(msg.get("result") or msg, ensure_ascii=False)[:500])
        assert kind == "run_complete", f"live run did not complete: {msg}"
        break
print("live guard events:", guard_hits)
PY
ls -lat /home/licodev/projects/agentforge/server/workspace | head -5
```
Expected: `node_start` lines for `input`/`planning`/`reasoning`/`review`, `run_complete` with a non-null `answer` (should be `72`), and — if the review asked for at least one refine — one or more `GUARD loop_guard {...'loopNodeId': 'loop_guard'...}` lines. The final `ls` shows a `server/workspace/<uuid>/` directory dated **today** (previously the newest was 7/14 — this is the concrete artifact that "it actually ran").

**Acceptance for this step:** `run_complete` with a non-null answer and no `error` event. `guard_hits == 0` is acceptable if the model's first answer passed review on the first pass (the guard only sits on the refine edge) — in that case re-run once with a deliberately unsatisfiable criterion appended to `"criteria"`, e.g. `[{"id": "c1", "text": "answer must cite a peer-reviewed source", "severity": "must_pass"}]`, to force refine passes and observe the guard. Record which variant produced the guard events.

**If the live model is unavailable:** record the exact error, mark this step BLOCKED, and state plainly in the final report that live `loop.guard` execution was not verified — do not report the work as complete-and-verified.

- [ ] **Step 8: Final repo hygiene check**

```bash
cd /home/licodev/projects/agentforge && git status --short && git log --oneline -12
```
Expected: the only dirty/untracked entries are the pre-existing `HANDOFF.md`, `start.sh`, `.agents/`, `.opencode/`, `agentforge`, plus the new `server/data/benchmark-*.json` and `server/workspace/<uuid>/` produced by Steps 6-7. The log shows this plan's commits in order.

- [ ] **Step 9: Commit the benchmark artifact**

```bash
cd /home/licodev/projects/agentforge && git add server/data/benchmark-*.json && git commit -m "chore: record post-loop-node GSM8K benchmark run"
```

---

## Self-Review

**1. Spec coverage** — every spec section and test-plan item mapped to a task:

| Spec | Task |
| --- | --- |
| §1 `loop.guard` manifest, `RUNTIMES` += `loop_guard`, GenericNode needs no custom renderer | 1 |
| §2 Delete `LoopPolicySchema`/`LoopPolicyGuardSchema`/`ArchitectureSchema.loopPolicies`, keep the two const arrays, drop store state + `loopPolicies: []`, drop the migration test | 8 |
| §3a Node registration branch + skip in the edge-wiring loop | 6 |
| §3b `_make_loop_guard_node` body unchanged, `policy_id` now the canvas node id | 6 |
| §3c `_loop_policy_from_config` adapter | 3 |
| §3d `_derive_loop_members` → `node_to_policies` → `loop_policy_ids` (llm_step/review/state untouched) | 4, 6 |
| §4 `_tarjan_scc` + `_validate_gated_cycles`, called after `_filter_control_edges`, before node registration; starter graph consequence | 5, 7, 10 |
| §5 Budget axes (token/cost/duration) | 6 (`test_loop_guard_max_tokens_trips_using_derived_members`) |
| §6 Stuck detection | 3 (threshold omission), 6 (`test_loop_guard_stuck_trips_from_review_progress_history`) |
| §7 `onExhaustion` exit/escalate → exit port; fail → exception; compile-time exit-port check | 6 |
| §8 `loopPolicyId` → `loopNodeId`, no `progress` field | 2 |
| §9 Four error cases (ungated cycle / exit unwired / loopBack unwired / fail trip); two sidecar errors deleted | 6, 7 |
| §10 Deletion list (orphans, live Lens, `_prepare_loop_policies`, sidecar FE, `loopPolicy.schema.test.ts`); frozen files | 6, 8, 9 (+ Task 6 Step 8 `git diff --stat` proves the frozen files are untouched) |
| Test plan 1 (compiler fixtures → node + edges) | 6, 7 |
| Test plan 2 (`test_loop_guard.py` unchanged) | 6 Step 8, 11 Step 3 |
| Test plan 3 (cycle validation, SCC cases ported from `loopCandidates.test.ts`) | 5, 7 |
| Test plan 4 (`_derive_loop_members`) | 4 |
| Test plan 5 (migration regression → starter graph with a guard) | 7 (delete + two replacements), 10, 11 |
| Test plan 6 (`loopNodeId`/iteration/budget/`exitReason` camelCase) | 2, 6, 11 |
| Test plan 7 (frontend GenericNode render, 5-axis config form) | 1 |

No gaps.

**2. Placeholder scan** — no `TBD`, no "add appropriate error handling", no "similar to Task N", no referenced-but-undefined symbols. Every code step carries the literal code. Task 11's two conditional branches (dead API key, guard not hit on the first live run) specify concrete fallback commands and an explicit BLOCKED reporting requirement rather than deferring the decision.

**3. Type consistency** — checked across tasks: `_loop_policy_from_config` / `_derive_loop_members` / `_tarjan_scc` / `_validate_gated_cycles` / `_handle_targets` are spelled identically in their defining task and every call site; `loopNodeId` (never `loopPolicyId`) after Task 2; port ids `in` / `loopBack` / `exit` and config keys `maxIterations, maxTokens, maxCostUsd, maxDurationSec, stuckWindow, stuckThreshold, onExhaustion` identical in `server/manifests.py`, `builtinManifests.ts`, `_loop_policy_from_config`, every test fixture, and `starterArchitecture.ts`; node id `loop_guard` and edge ids `e9`/`e10` identical in Task 10 and Task 11's Python mirror; `loop_policy_ids` retained as the parameter name on `_make_llm_step_node` / `_make_review_node` per spec §3d.

**Fixed during review:** three issues found and corrected inline before finalizing —
- Task 3's adapter originally followed the spec snippet verbatim and would have injected `threshold: None`, crashing `_is_stuck` with `float(None)`; the adapter now omits the key and a test pins the behavior.
- Task 7 originally didn't touch `test_compile_no_entry_raises`, which would have started failing with the wrong error message the moment cycle validation was wired; it's now rewritten as a *gated* entry-less cycle.
- Task 9 originally stopped at the three files named in the spec; `useUiStore`'s six loop-lens members and the two `uiStore.test.ts` describe blocks would have been left as dead state, so they're now part of the task.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-07-loop-node-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

- If Subagent-Driven: **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development` — fresh subagent per task + two-stage review.
- If Inline: **REQUIRED SUB-SKILL:** `superpowers:executing-plans` — batch execution with checkpoints for review.
