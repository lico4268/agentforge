# LoopPolicy Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠️ Superseded:** this plan (the sidecar `LoopPolicy` model) was fully replaced by
> `docs/superpowers/plans/2026-08-07-loop-node-implementation.md` — see that plan instead.

**Goal:** Make `LoopPolicy` a persisted, executable contract — stored on `Architecture`, migrated safely from policy-less graphs, enforced by `compile_graph` through a shared synthetic guard node, and reported over WebSocket events — per `docs/superpowers/specs/2026-08-06-loop-policy-design.md`.

**Architecture:** A `LoopPolicy` array lives on `Architecture` (frontend Zod schema, backend reads it as an untyped dict field like `nodes`/`edges`). At compile time, `compile_graph` validates each policy and splices a synthetic `__loop_guard__<id>` node into the graph between a feedback edge's source and its original target, using LangGraph's `Command(goto=...)` pattern. The guard reads/writes a new `AgentState.loop_runtime` field (a custom-reducer dict keyed by policy id) to track iteration/token/cost/duration/stuck signals, independent of the node types it wraps. Token/cost data reaches `loop_runtime` via a new optional `usage_sink` out-parameter on `run_llm_step`, so `baseline.py`/`treatment.py` (which never pass it) are completely unaffected.

**Tech Stack:** Python 3.12, FastAPI, LangGraph `StateGraph`/`Command`, Pydantic-free dict-based Architecture handling, pytest + pytest-asyncio (`asyncio_mode=auto`); TypeScript, Zod, Vitest.

## Global Constraints

- Wire-format fields are camelCase on both sides — backend Python dict keys sent via `to_frontend()` match the frontend Zod schema field-for-field, no snake_case leaking through (AGENTS.md, CLAUDE.md "타입 계약").
- External LLM calls are mocked in every test — no network or real API keys (AGENTS.md §6, already the pattern in `server/tests/`).
- New backend validation errors are raised as `ValueError` at compile time, matching `compile_graph`'s existing style (`"Unknown node type: ..."`, `"Architecture has no entry node..."`).
- Policy-less Architectures (missing or empty `loopPolicies`) must produce byte-for-byte identical execution to today — this is the migration safety guarantee the whole design rests on.
- Backend verification: `cd server && ../server/.venv/bin/ruff check .`, `../server/.venv/bin/ruff format .`, `../server/.venv/bin/python -m pytest` (the venv's `pytest` executable has a broken shebang — always invoke via `python -m pytest`).
- Frontend verification: `cd ui && npm run lint && npm run build && npm run test` (`npm run build` runs `tsc -b`, which catches type errors `tsc --noEmit` misses — always use `npm run build` as the final check).
- Do not modify `start.sh`, `.agents/`, `.opencode/`, or `agentforge` — pre-existing uncommitted user work outside this plan's scope.
- Out of scope (per the spec's non-goals): the Loop Lens policy-editing UI, frontend rendering of `loopRuntime` in the Loops panel, the `retry` loop kind, and generalizing loop guards to node types beyond `review.intent`/`human.checkpoint`.

---

## File Structure

| File | Change |
| --- | --- |
| `ui/src/types/graph.ts` | Add `LoopPolicyGuardSchema`, `LoopPolicySchema`, `loopPolicies` field on `ArchitectureSchema` |
| `ui/src/stores/useGraphStore.ts` | Carry `loopPolicies` through `loadArchitecture`/`toArchitecture` |
| `ui/src/types/events.ts` | Add `LoopRuntimeSchema`, `loopRuntime` field on `ExecutionEventSchema` |
| `server/state.py` | Add `LoopRuntimeState`, `empty_loop_runtime`, `merge_loop_runtime`, `AgentState.loop_runtime` |
| `server/events.py` | Add `loop_runtime` to `ExecutionEvent` |
| `server/nodes/loop_guard.py` (new) | `evaluate_loop_guard` (pure guard evaluation), `next_runtime` (iteration/timer bump) |
| `server/graphs/compile.py` | `_prepare_loop_policies`, `_make_loop_guard_node`, wiring changes to node registration + edge wiring |
| `server/nodes/llm_step.py` | `usage_sink` out-parameter on `run_llm_step`/`_emit_token_usage` |
| `server/nodes/review.py` | `loop_policy_ids` param on `make_review`, budget + progress-signal contribution |
| Test files | `ui/src/__tests__/loopPolicy.schema.test.ts` (new), `ui/src/__tests__/graphStore.test.ts`, `ui/src/__tests__/events.schema.test.ts`, `server/tests/test_state.py` (new), `server/tests/test_events.py`, `server/tests/test_loop_guard.py` (new), `server/tests/test_compile.py`, `server/tests/test_llm_step_policy.py` |

---

### Task 1: Frontend — `LoopPolicy` schema, `Architecture.loopPolicies`, store round-trip

**Files:**
- Modify: `ui/src/types/graph.ts`
- Modify: `ui/src/stores/useGraphStore.ts`
- Test: `ui/src/__tests__/loopPolicy.schema.test.ts` (create)
- Test: `ui/src/__tests__/graphStore.test.ts` (extend)

**Interfaces:**
- Produces: `LoopPolicyGuardSchema`, `LoopPolicySchema`, `LoopPolicy` type, `LOOP_POLICY_KINDS`, `LOOP_POLICY_EXHAUSTION_ACTIONS` (all exported from `ui/src/types/graph.ts`, re-exported via `ui/src/types/index.ts`'s existing `export * from './graph'`). `Architecture.loopPolicies: LoopPolicy[]`. `GraphState.loopPolicies: LoopPolicy[]` on the zustand store.

- [ ] **Step 1: Write the failing schema test**

Create `ui/src/__tests__/loopPolicy.schema.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { LoopPolicySchema, ArchitectureSchema } from '@/types'

describe('LoopPolicySchema', () => {
  it('유효한 LoopPolicy를 통과시킨다', () => {
    const policy = {
      id: 'loop-1',
      kind: 'critiqueRevise',
      feedbackEdgeIds: ['e-review-reasoning'],
      memberNodeIds: ['reasoning', 'review'],
      exitEdgeIds: ['e-review-output'],
      guard: { maxIterations: 3, stuck: { window: 3, threshold: 1 } },
      onExhaustion: 'exit',
    }
    const parsed = LoopPolicySchema.parse(policy)
    expect(parsed.guard.maxIterations).toBe(3)
    expect(parsed.guard.stuck?.window).toBe(3)
  })

  it('알 수 없는 kind는 거부한다 (v1은 retry 미지원)', () => {
    const bad = {
      id: 'loop-1',
      kind: 'retry',
      feedbackEdgeIds: [],
      memberNodeIds: [],
      exitEdgeIds: [],
      guard: {},
      onExhaustion: 'exit',
    }
    expect(() => LoopPolicySchema.parse(bad)).toThrow()
  })

  it('알 수 없는 onExhaustion은 거부한다', () => {
    const bad = {
      id: 'loop-1',
      kind: 'critiqueRevise',
      feedbackEdgeIds: [],
      memberNodeIds: [],
      exitEdgeIds: [],
      guard: {},
      onExhaustion: 'retry-forever',
    }
    expect(() => LoopPolicySchema.parse(bad)).toThrow()
  })
})

describe('ArchitectureSchema loopPolicies migration', () => {
  it('loopPolicies 키가 없는 기존 Architecture를 빈 배열로 채운다', () => {
    const legacy = {
      version: '0.1',
      metadata: { name: 'legacy', createdAt: '2026-01-01T00:00:00.000Z' },
      nodes: [],
      edges: [],
    }
    const parsed = ArchitectureSchema.parse(legacy)
    expect(parsed.loopPolicies).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/loopPolicy.schema.test.ts`
Expected: FAIL — `LoopPolicySchema` is not exported from `@/types`.

- [ ] **Step 3: Add the schema to `ui/src/types/graph.ts`**

Insert after `GraphEdgeSchema`/`GraphEdge` (before `ArchitectureSchema`):

```ts
export const LoopPolicyGuardSchema = z.object({
  maxIterations: z.number().optional(),
  maxTokens: z.number().optional(),
  maxCostUsd: z.number().optional(),
  maxDurationSec: z.number().optional(),
  stuck: z
    .object({
      window: z.number(),
      threshold: z.number().optional(),
    })
    .optional(),
})
export type LoopPolicyGuard = z.infer<typeof LoopPolicyGuardSchema>

export const LOOP_POLICY_KINDS = ['evaluatorOptimizer', 'critiqueRevise', 'humanReview'] as const
export const LOOP_POLICY_EXHAUSTION_ACTIONS = ['exit', 'escalate', 'fail'] as const

/**
 * Executable loop configuration, distinct from a detected cycle (`LoopCandidate`
 * in `canvas/loops/loopAnchors.ts`). `kind` is descriptive only — the compiler
 * never branches on it. See docs/superpowers/specs/2026-08-06-loop-policy-design.md.
 */
export const LoopPolicySchema = z.object({
  id: z.string(),
  kind: z.enum(LOOP_POLICY_KINDS),
  feedbackEdgeIds: z.array(z.string()),
  memberNodeIds: z.array(z.string()),
  exitEdgeIds: z.array(z.string()),
  guard: LoopPolicyGuardSchema,
  onExhaustion: z.enum(LOOP_POLICY_EXHAUSTION_ACTIONS),
})
export type LoopPolicy = z.infer<typeof LoopPolicySchema>
```

Then add the field to `ArchitectureSchema`:

```ts
export const ArchitectureSchema = z.object({
  version: z.string().default('0.1'),
  metadata: z.object({
    name: z.string(),
    description: z.string().optional(),
    createdAt: z.string(),
  }),
  nodes: z.array(GraphNodeSchema).default([]),
  edges: z.array(GraphEdgeSchema).default([]),
  loopPolicies: z.array(LoopPolicySchema).default([]),
})
export type Architecture = z.infer<typeof ArchitectureSchema>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/loopPolicy.schema.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing store round-trip test**

In `ui/src/__tests__/graphStore.test.ts`, add `loopPolicies` to the existing `architecture` fixture (after `edges`):

```ts
  loopPolicies: [
    {
      id: 'loop-1',
      kind: 'critiqueRevise' as const,
      feedbackEdgeIds: ['planning-to-review'],
      memberNodeIds: ['planning', 'review'],
      exitEdgeIds: ['planning-to-review'],
      guard: { maxIterations: 3 },
      onExhaustion: 'exit' as const,
    },
  ],
```

And add a new `it()` block inside the existing `describe('useGraphStore architecture serialization', ...)`, right after the "preserves edge identities..." test:

```ts
  it('preserves loop policies through load and serialize', () => {
    const result = useGraphStore.getState().toArchitecture('serialized')

    expect(result.loopPolicies).toEqual(architecture.loopPolicies)
  })
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/graphStore.test.ts`
Expected: FAIL — `result.loopPolicies` is `undefined`, not equal to the fixture array.

- [ ] **Step 7: Wire `loopPolicies` through the store**

In `ui/src/stores/useGraphStore.ts`:

Change the import line:
```ts
import type { Architecture, GraphNode, LoopPolicy } from '@/types'
```

Add to `GraphState` (after `edges: Edge[]`):
```ts
  loopPolicies: LoopPolicy[]
```

Add to the store's initial state (after `edges: [],`):
```ts
  loopPolicies: [],
```

In `loadArchitecture`, add `loopPolicies: arch.loopPolicies,` to the `set({...})` object (after the `edges:` line).

In `toArchitecture`, destructure `loopPolicies` alongside `nodes`/`edges` and include it in the returned object:
```ts
  toArchitecture: (name) => {
    const { nodes, edges, loopPolicies } = get()
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
      loopPolicies,
    }
  },
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/graphStore.test.ts src/__tests__/loopPolicy.schema.test.ts`
Expected: PASS (all tests, including the pre-existing ones — confirms no regression)

- [ ] **Step 9: Type-check and build**

Run: `cd ui && npm run build`
Expected: PASS — no TypeScript errors.

- [ ] **Step 10: Commit**

```bash
git add ui/src/types/graph.ts ui/src/stores/useGraphStore.ts ui/src/__tests__/loopPolicy.schema.test.ts ui/src/__tests__/graphStore.test.ts
git commit -m "feat(ui): add LoopPolicy schema and Architecture.loopPolicies persistence"
```

---

### Task 2: Backend — `AgentState.loop_runtime` and the `merge_loop_runtime` reducer

**Files:**
- Modify: `server/state.py`
- Test: `server/tests/test_state.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `LoopRuntimeState` (TypedDict: `iteration: int`, `total_tokens: int`, `total_cost_usd: float`, `started_at: float`, `last_feedback: str | None`, `progress_history: list[float]`), `empty_loop_runtime() -> LoopRuntimeState`, `merge_loop_runtime(existing, new) -> dict[str, LoopRuntimeState]`, `AgentState.loop_runtime: Annotated[dict[str, LoopRuntimeState], merge_loop_runtime]`. These are consumed by Task 4 (`nodes/loop_guard.py`) and Task 5 (`graphs/compile.py`).

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_state.py`:

```python
"""state.py — loop_runtime 병합 reducer 단위 테스트."""

from state import empty_loop_runtime, initial_state, merge_loop_runtime


def test_initial_state_has_empty_loop_runtime():
    state = initial_state("task")
    assert state["loop_runtime"] == {}


def test_merge_loop_runtime_sums_tokens_and_cost():
    existing = {"loop-1": {**empty_loop_runtime(), "total_tokens": 100, "total_cost_usd": 0.01}}
    new = {"loop-1": {"total_tokens": 50, "total_cost_usd": 0.02}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["total_tokens"] == 150
    assert round(merged["loop-1"]["total_cost_usd"], 4) == 0.03


def test_merge_loop_runtime_replaces_iteration_and_started_at():
    existing = {"loop-1": {**empty_loop_runtime(), "iteration": 1, "started_at": 10.0}}
    new = {"loop-1": {"iteration": 2, "started_at": 10.0}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["iteration"] == 2
    assert merged["loop-1"]["started_at"] == 10.0


def test_merge_loop_runtime_leaves_unset_fields_untouched():
    existing = {"loop-1": {**empty_loop_runtime(), "iteration": 3, "total_tokens": 200}}
    # 토큰만 기여하는 멤버 노드의 부분 업데이트 — iteration은 그대로 유지돼야 한다.
    new = {"loop-1": {"total_tokens": 10}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["iteration"] == 3
    assert merged["loop-1"]["total_tokens"] == 210


def test_merge_loop_runtime_appends_progress_history():
    existing = {"loop-1": {**empty_loop_runtime(), "progress_history": [3.0, 2.0]}}
    new = {"loop-1": {"progress_history": [1.0]}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["progress_history"] == [3.0, 2.0, 1.0]


def test_merge_loop_runtime_initializes_unknown_policy():
    merged = merge_loop_runtime({}, {"loop-1": {"iteration": 1, "total_tokens": 5}})

    assert merged["loop-1"]["iteration"] == 1
    assert merged["loop-1"]["total_tokens"] == 5
    assert merged["loop-1"]["progress_history"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'empty_loop_runtime' from 'state'`.

- [ ] **Step 3: Implement in `server/state.py`**

Replace the full file contents with:

```python
from typing import Annotated, TypedDict


class LoopRuntimeState(TypedDict):
    iteration: int
    total_tokens: int
    total_cost_usd: float
    started_at: float
    last_feedback: str | None
    progress_history: list[float]


def empty_loop_runtime() -> LoopRuntimeState:
    return LoopRuntimeState(
        iteration=0,
        total_tokens=0,
        total_cost_usd=0.0,
        started_at=0.0,
        last_feedback=None,
        progress_history=[],
    )


def merge_loop_runtime(
    existing: dict[str, LoopRuntimeState], new: dict[str, LoopRuntimeState]
) -> dict[str, LoopRuntimeState]:
    """LoopPolicy별 loop_runtime 병합 reducer.

    iteration/started_at/last_feedback는 새 값이 있으면 교체한다(단일 writer —
    가드 노드가 iteration/started_at을, review 노드가 last_feedback을 쓴다).
    total_tokens/total_cost_usd/progress_history는 여러 루프 멤버 노드가 각자의
    기여분만 부분 업데이트로 보내므로 누적한다(합산/append).
    """
    merged = dict(existing)
    for policy_id, update in new.items():
        current = merged.get(policy_id, empty_loop_runtime())
        merged[policy_id] = LoopRuntimeState(
            iteration=update.get("iteration", current["iteration"]),
            total_tokens=current["total_tokens"] + update.get("total_tokens", 0),
            total_cost_usd=current["total_cost_usd"] + update.get("total_cost_usd", 0.0),
            started_at=update.get("started_at", current["started_at"]),
            last_feedback=update.get("last_feedback", current["last_feedback"]),
            progress_history=current["progress_history"] + update.get("progress_history", []),
        )
    return merged


class AgentState(TypedDict):
    task: str
    task_tags: list[str]
    intent: str | None  # 원본 의도 — 없으면 review가 task 자체를 의도로 간주
    plan: list[str] | None
    answer: str | None
    confidence: float | None  # ReasonOut 참고 지표 (라우팅 미사용)
    criteria: list[dict]  # Criterion.model_dump() 목록
    review_delta: dict | None  # ReviewDelta.model_dump()
    review_branch: str | None  # review 노드가 확정한 accept/refine/clarify (라우터가 읽음)
    retries: int
    feedback: str | None  # 직전 리뷰의 unmet delta → 재작업 입력
    batch_mode: bool  # True면 clarify → accept 강등 (interrupt 불가 환경)
    matched_cards: list[str]  # classify가 매칭한 판단 카드 id 목록
    loop_runtime: Annotated[dict[str, LoopRuntimeState], merge_loop_runtime]


def initial_state(
    task: str,
    task_tags: list[str] | None = None,
    batch_mode: bool = False,
    intent: str | None = None,
    criteria: list[dict] | None = None,
) -> AgentState:
    return AgentState(
        task=task,
        task_tags=task_tags or [],
        intent=intent,
        plan=None,
        answer=None,
        confidence=None,
        criteria=criteria or [],
        review_delta=None,
        review_branch=None,
        retries=0,
        feedback=None,
        batch_mode=batch_mode,
        matched_cards=[],
        loop_runtime={},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_state.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd server && ../server/.venv/bin/python -m pytest`
Expected: PASS — every existing test still passes (`initial_state`'s new `loop_runtime={}` field is additive, no existing test asserts an exhaustive `AgentState` shape).

- [ ] **Step 6: Commit**

```bash
git add server/state.py server/tests/test_state.py
git commit -m "feat(server): add AgentState.loop_runtime with a per-policy merge reducer"
```

---

### Task 3: Event contract — `loopRuntime` on `ExecutionEvent` (backend + frontend)

**Files:**
- Modify: `server/events.py`
- Modify: `ui/src/types/events.ts`
- Test: `server/tests/test_events.py` (extend)
- Test: `ui/src/__tests__/events.schema.test.ts` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ExecutionEvent(..., loop_runtime: dict | None = None)`, `ExecutionEvent.to_frontend()` includes `loopRuntime` when set, `ExecutionEvent.model_dump()` includes `loop_runtime`. Frontend `LoopRuntimeSchema`, `ExecutionEventSchema.loopRuntime`. Consumed by Task 5's guard node, which will call `make_event(..., "node_end", loop_runtime={...})`.

- [ ] **Step 1: Write the failing backend test**

In `server/tests/test_events.py`, change the import line from `from events import make_error_event` to `from events import make_error_event, make_event`, then add:

```python
def test_to_frontend_includes_loop_runtime_camelcase():
    ev = make_event(
        "run-1",
        "__loop_guard__loop-1",
        "node_end",
        loop_runtime={"loopPolicyId": "loop-1", "iteration": 2, "exitReason": "maxIterations"},
    )
    payload = ev.to_frontend()

    assert payload["loopRuntime"] == {
        "loopPolicyId": "loop-1",
        "iteration": 2,
        "exitReason": "maxIterations",
    }


def test_to_frontend_omits_loop_runtime_when_absent():
    ev = make_event("run-1", "reasoning", "node_start")
    assert "loopRuntime" not in ev.to_frontend()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_events.py -v`
Expected: FAIL — `TypeError: ExecutionEvent.__init__() got an unexpected keyword argument 'loop_runtime'`.

- [ ] **Step 3: Add `loop_runtime` to `ExecutionEvent`**

In `server/events.py`, add `"loop_runtime"` to the `__slots__` tuple (after `"policy_decision"`):

```python
    __slots__ = (
        "event_type",
        "run_id",
        "node_id",
        "timestamp",
        "duration_ms",
        "input",
        "output",
        "token_usage",
        "policy_decision",
        "loop_runtime",
        "message",
        "error",
    )
```

Add the parameter to `__init__` (after `policy_decision`) and set it:

```python
    def __init__(
        self,
        event_type: str,
        run_id: str,
        node_id: str,
        *,
        duration_ms: int | None = None,
        input: Any = None,
        output: Any = None,
        token_usage: dict | None = None,
        policy_decision: dict | None = None,
        loop_runtime: dict | None = None,
        message: str | None = None,
        error: dict | None = None,
    ) -> None:
        self.event_type = event_type
        self.run_id = run_id
        self.node_id = node_id
        self.timestamp = datetime.now(UTC).isoformat()
        self.duration_ms = duration_ms
        self.input = input
        self.output = output
        self.token_usage = token_usage
        self.policy_decision = policy_decision
        self.loop_runtime = loop_runtime
        self.message = message
        self.error = error
```

Add to `to_frontend()` (after the `policy_decision` block):

```python
        if self.loop_runtime is not None:
            d["loopRuntime"] = self.loop_runtime
```

Add to `model_dump()` (after `"policy_decision": self.policy_decision,`):

```python
            "loop_runtime": self.loop_runtime,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_events.py -v`
Expected: PASS (6 tests: 4 pre-existing + 2 new)

- [ ] **Step 5: Write the failing frontend test**

In `ui/src/__tests__/events.schema.test.ts`, add inside the `describe('ExecutionEventSchema', ...)` block:

```ts
  it('loopRuntime 필드를 보존한다', () => {
    const payload = {
      eventType: 'node_end',
      runId: 'run-1',
      nodeId: '__loop_guard__loop-1',
      timestamp: new Date().toISOString(),
      loopRuntime: {
        loopPolicyId: 'loop-1',
        iteration: 2,
        maxIterations: 5,
        exitReason: 'maxIterations',
      },
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.loopRuntime?.loopPolicyId).toBe('loop-1')
    expect(parsed.loopRuntime?.exitReason).toBe('maxIterations')
  })

  it('loopRuntime 없이도 이벤트를 통과시킨다(옵션 필드)', () => {
    const payload = {
      eventType: 'node_start',
      runId: 'run-1',
      nodeId: 'reasoning',
      timestamp: new Date().toISOString(),
    }
    const parsed = ExecutionEventSchema.parse(payload)
    expect(parsed.loopRuntime).toBeUndefined()
  })
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/events.schema.test.ts`
Expected: FAIL — `loopRuntime` is stripped/undefined-mismatch because the schema doesn't declare it (Zod drops unknown keys by default, so `parsed.loopRuntime` is `undefined` even though the payload set it — the first new test fails on `expect(parsed.loopRuntime?.loopPolicyId).toBe('loop-1')`).

- [ ] **Step 7: Add `LoopRuntimeSchema` to `ui/src/types/events.ts`**

Insert after `ExecutionErrorSchema`/`ExecutionError` (before `ExecutionEventSchema`):

```ts
export const LOOP_RUNTIME_EXIT_REASONS = [
  'success',
  'maxIterations',
  'budget',
  'stuck',
  'escalated',
  'failed',
] as const

/** Per-pass snapshot from a compiler-inserted loop guard node — see
 * docs/superpowers/specs/2026-08-06-loop-policy-design.md §7. Keyed by
 * loopPolicyId, not nodeId — the guard node's id is synthetic and has no
 * canvas representation. */
export const LoopRuntimeSchema = z.object({
  loopPolicyId: z.string(),
  iteration: z.number(),
  maxIterations: z.number().optional(),
  tokens: z.number().optional(),
  costUsd: z.number().optional(),
  durationMs: z.number().optional(),
  lastFeedback: z.string().optional(),
  progress: z.enum(['converging', 'plateauing', 'stuck']).optional(),
  exitReason: z.enum(LOOP_RUNTIME_EXIT_REASONS).optional(),
})
export type LoopRuntime = z.infer<typeof LoopRuntimeSchema>
```

Add the field to `ExecutionEventSchema` (after `policyDecision: PolicyDecisionSchema.optional(),`):

```ts
  loopRuntime: LoopRuntimeSchema.optional(),
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/events.schema.test.ts`
Expected: PASS (6 tests: 4 pre-existing + 2 new)

- [ ] **Step 9: Full verification**

Run: `cd server && ../server/.venv/bin/python -m pytest` and `cd ui && npm run build && npm run test`
Expected: PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add server/events.py server/tests/test_events.py ui/src/types/events.ts ui/src/__tests__/events.schema.test.ts
git commit -m "feat: add loopRuntime field to the ExecutionEvent contract"
```

---

### Task 4: Backend — `evaluate_loop_guard` pure guard-evaluation core

**Files:**
- Create: `server/nodes/loop_guard.py`
- Test: `server/tests/test_loop_guard.py` (create)

**Interfaces:**
- Consumes: `LoopRuntimeState`, `empty_loop_runtime` from `state.py` (Task 2).
- Produces: `evaluate_loop_guard(policy: dict, runtime: LoopRuntimeState) -> GuardResult` where `GuardResult = TypedDict('GuardResult', {'should_continue': bool, 'exit_reason': str | None})`; `next_runtime(prior: LoopRuntimeState | None) -> LoopRuntimeState`. Both are pure — no LangGraph, no I/O. Consumed by Task 5's `_make_loop_guard_node` in `graphs/compile.py`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_loop_guard.py`:

```python
"""nodes/loop_guard.py — 순수 가드 평가 함수 단위 테스트. LangGraph 의존 없음."""

import time

from nodes.loop_guard import evaluate_loop_guard, next_runtime
from state import empty_loop_runtime


def _policy(**guard) -> dict:
    return {
        "id": "loop-1",
        "kind": "critiqueRevise",
        "feedbackEdgeIds": ["e1"],
        "memberNodeIds": [],
        "exitEdgeIds": ["e2"],
        "guard": guard,
        "onExhaustion": "exit",
    }


def test_no_guard_configured_always_continues():
    runtime = next_runtime(None)
    result = evaluate_loop_guard(_policy(), runtime)
    assert result == {"should_continue": True, "exit_reason": None}


def test_max_iterations_trips_when_exceeded():
    policy = _policy(maxIterations=2)
    runtime = {**empty_loop_runtime(), "iteration": 3}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "maxIterations"}


def test_max_iterations_allows_up_to_limit():
    policy = _policy(maxIterations=2)
    runtime = {**empty_loop_runtime(), "iteration": 2}
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_max_tokens_trips_when_exceeded():
    policy = _policy(maxTokens=1000)
    runtime = {**empty_loop_runtime(), "iteration": 1, "total_tokens": 1200}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_max_cost_trips_when_exceeded():
    policy = _policy(maxCostUsd=0.5)
    runtime = {**empty_loop_runtime(), "iteration": 1, "total_cost_usd": 0.6}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_max_duration_trips_when_exceeded():
    policy = _policy(maxDurationSec=1)
    runtime = {**empty_loop_runtime(), "iteration": 1, "started_at": time.time() - 5}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_stuck_trips_when_progress_history_plateaus():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {
        **empty_loop_runtime(),
        "iteration": 3,
        "progress_history": [4.0, 4.0, 4.0],  # 3회 동안 개선 없음
    }
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "stuck"}


def test_stuck_does_not_trip_before_window_is_full():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {**empty_loop_runtime(), "iteration": 2, "progress_history": [4.0, 4.0]}
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_stuck_does_not_trip_when_improving():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {
        **empty_loop_runtime(),
        "iteration": 3,
        "progress_history": [4.0, 2.0, 0.0],  # 개선폭 4 >= threshold 1
    }
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_next_runtime_increments_iteration_and_fixes_started_at():
    first = next_runtime(None)
    assert first["iteration"] == 1
    assert first["started_at"] > 0

    second = next_runtime(first)
    assert second["iteration"] == 2
    assert second["started_at"] == first["started_at"]  # 최초 시각 고정
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_loop_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.loop_guard'`.

- [ ] **Step 3: Implement `server/nodes/loop_guard.py`**

```python
"""LoopPolicy.guard 5축(iteration/token/cost/duration/stuck) 순수 평가 로직.

LangGraph·이벤트 방출과 완전히 분리돼 있다 — graphs/compile.py의
_make_loop_guard_node가 이 모듈을 호출해 실제 그래프 라우팅에 반영한다.
새 가드 축이 추가되면 여기와 state.LoopRuntimeState만 넓히면 되고, 컴파일러
배선(어떤 노드 타입이 가드를 받는지)은 다시 건드릴 필요가 없다.
"""

import time
from typing import Literal, TypedDict

from state import LoopRuntimeState, empty_loop_runtime

ExitReason = Literal["success", "maxIterations", "budget", "stuck", "escalated", "failed"]


class GuardResult(TypedDict):
    should_continue: bool
    exit_reason: ExitReason | None


def evaluate_loop_guard(policy: dict, runtime: LoopRuntimeState) -> GuardResult:
    """policy["guard"]의 축을 순서대로 확인한다. 하나라도 트립되면 즉시 종료 판정.

    runtime은 이번 패스분(iteration 증가분 포함)까지 반영된 값을 넘겨야 한다
    (next_runtime()이 만든 값). 이 함수 자체는 iteration을 증가시키지 않는다.
    """
    guard = policy.get("guard") or {}

    max_iterations = guard.get("maxIterations")
    if max_iterations is not None and runtime["iteration"] > max_iterations:
        return {"should_continue": False, "exit_reason": "maxIterations"}

    max_tokens = guard.get("maxTokens")
    if max_tokens is not None and runtime["total_tokens"] > max_tokens:
        return {"should_continue": False, "exit_reason": "budget"}

    max_cost = guard.get("maxCostUsd")
    if max_cost is not None and runtime["total_cost_usd"] > max_cost:
        return {"should_continue": False, "exit_reason": "budget"}

    max_duration = guard.get("maxDurationSec")
    if max_duration is not None and (time.time() - runtime["started_at"]) > max_duration:
        return {"should_continue": False, "exit_reason": "budget"}

    stuck_cfg = guard.get("stuck")
    if stuck_cfg is not None and _is_stuck(runtime["progress_history"], stuck_cfg):
        return {"should_continue": False, "exit_reason": "stuck"}

    return {"should_continue": True, "exit_reason": None}


def _is_stuck(progress_history: list[float], stuck_cfg: dict) -> bool:
    """window 구간의 진행 신호(낮을수록 좋음, 예: unmet 기준 개수) 개선폭이
    threshold 미만이면 stuck. 기록이 window보다 적으면 아직 판단하지 않는다.
    """
    window = int(stuck_cfg.get("window", 0))
    threshold = float(stuck_cfg.get("threshold", 0))
    if window <= 0 or len(progress_history) < window:
        return False
    recent = progress_history[-window:]
    improvement = recent[0] - recent[-1]
    return improvement < threshold


def next_runtime(prior: LoopRuntimeState | None) -> LoopRuntimeState:
    """가드 진입 시 호출 — iteration을 1 증가시키고 started_at을 최초 1회만 고정한다."""
    base = prior or empty_loop_runtime()
    return {
        "iteration": base["iteration"] + 1,
        "total_tokens": base["total_tokens"],
        "total_cost_usd": base["total_cost_usd"],
        "started_at": base["started_at"] or time.time(),
        "last_feedback": base["last_feedback"],
        "progress_history": base["progress_history"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_loop_guard.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Lint**

Run: `cd server && ../server/.venv/bin/ruff check . && ../server/.venv/bin/ruff format --check .`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/nodes/loop_guard.py server/tests/test_loop_guard.py
git commit -m "feat(server): add evaluate_loop_guard pure guard-evaluation core"
```

---

### Task 5: Backend — compiler wiring (validation, guard node insertion, `onExhaustion` routing)

This is the walking-skeleton task: it proves the whole Approach-B mechanism end-to-end using `maxIterations` (needs no extra plumbing beyond Tasks 2–4) before Task 6 layers on token/cost.

**Files:**
- Modify: `server/graphs/compile.py`
- Test: `server/tests/test_compile.py` (extend)

**Interfaces:**
- Consumes: `merge_loop_runtime`/`LoopRuntimeState` (Task 2), `loop_runtime` event field (Task 3), `evaluate_loop_guard`/`next_runtime` (Task 4).
- Produces: `_prepare_loop_policies(loop_policies, nodes_by_id, edges_by_id) -> tuple[dict[str, str], list[dict], dict[str, list[str]]]` (returns `edge_target_override`, `guard_specs`, `node_to_policies`), `_make_loop_guard_node(policy, continue_target, exit_target, emit, run_id)`. `node_to_policies` is consumed by Task 6 (threaded into `_make_llm_step_node`/`_make_review_node`).

- [ ] **Step 1: Write the failing validation tests**

In `server/tests/test_compile.py`, add this helper near the top (after `_delta`):

```python
def _loop_policy(**overrides) -> dict:
    base = {
        "id": "loop-1",
        "kind": "critiqueRevise",
        "feedbackEdgeIds": [],
        "memberNodeIds": [],
        "exitEdgeIds": [],
        "guard": {},
        "onExhaustion": "exit",
    }
    base.update(overrides)
    return base
```

Then add these test functions:

```python
async def test_loop_policy_unknown_feedback_edge_raises(monkeypatch):
    _patch_model(monkeypatch)
    arch = _arch(
        [_node("reasoning", "reasoning.cot"), _node("review", "review.intent")],
        [_edge("reasoning", "review", "answer"), _edge("review", "reasoning", "refine")],
    )
    arch["loopPolicies"] = [_loop_policy(feedbackEdgeIds=["missing-edge"])]
    with pytest.raises(ValueError, match="unknown feedbackEdgeId"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_policy_feedback_edge_wrong_source_type_raises(monkeypatch):
    _patch_model(monkeypatch)
    plain_edge = _edge("reasoning", "review", "answer")
    arch = _arch(
        [_node("reasoning", "reasoning.cot"), _node("review", "review.intent")],
        [plain_edge, _edge("review", "reasoning", "refine")],
    )
    arch["loopPolicies"] = [_loop_policy(feedbackEdgeIds=[plain_edge["id"]])]
    with pytest.raises(ValueError, match="does not support loop guards"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_policy_mismatched_feedback_targets_raises(monkeypatch):
    _patch_model(monkeypatch)
    refine_edge = _edge("review", "reasoning", "refine")
    other_edge = _edge("review", "output", "clarify")
    arch = _arch(
        [
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [_edge("reasoning", "review", "answer"), refine_edge, other_edge],
    )
    arch["loopPolicies"] = [_loop_policy(feedbackEdgeIds=[refine_edge["id"], other_edge["id"]])]
    with pytest.raises(ValueError, match="single re-entry"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_policy_exit_without_exit_edges_raises(monkeypatch):
    _patch_model(monkeypatch)
    refine_edge = _edge("review", "reasoning", "refine")
    arch = _arch(
        [_node("reasoning", "reasoning.cot"), _node("review", "review.intent")],
        [_edge("reasoning", "review", "answer"), refine_edge],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            exitEdgeIds=[],
            onExhaustion="exit",
        )
    ]
    with pytest.raises(ValueError, match="requires a non-empty exitEdgeIds"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k loop_policy -v`
Expected: FAIL — `compile_graph` currently ignores `architecture["loopPolicies"]` entirely, so none of these raise.

- [ ] **Step 3: Add imports and `_prepare_loop_policies` to `server/graphs/compile.py`**

Replace the file's import block (currently lines 1–21) with:

```python
import time
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import config
from events import EventEmitter, make_event
from manifests import BUILTIN_MANIFESTS
from models import CallPolicy, Criterion, ModelSettings, PlanOut, ReasonOut, build_model
from nodes.checkpoint import make_human_checkpoint
from nodes.llm_step import run_llm_step
from nodes.loop_guard import evaluate_loop_guard, next_runtime
from nodes.policy import make_route_review
from nodes.review import make_review
from state import AgentState
```

Add this function after `_filter_control_edges` (before `compile_graph`):

```python
def _prepare_loop_policies(
    loop_policies: list[dict], nodes_by_id: dict[str, dict], edges_by_id: dict[str, dict]
) -> tuple[dict[str, str], list[dict], dict[str, list[str]]]:
    """LoopPolicy 목록을 검증하고, 컴파일러가 쓸 세 가지 파생 구조를 만든다.

    - edge_target_override: feedbackEdgeId → guard 노드 id (조건부 라우팅 재작성용)
    - guard_specs: 각 정책의 guard 노드 등록에 필요한 정보
    - node_to_policies: memberNodeId → 소속 정책 id 목록 (토큰/비용 귀속용, Task 6)
    """
    edge_target_override: dict[str, str] = {}
    guard_specs: list[dict] = []
    node_to_policies: dict[str, list[str]] = {}

    for policy in loop_policies:
        policy_id = policy["id"]
        guard_node_id = f"__loop_guard__{policy_id}"

        feedback_edges = []
        for edge_id in policy["feedbackEdgeIds"]:
            edge = edges_by_id.get(edge_id)
            if edge is None:
                raise ValueError(
                    f"LoopPolicy {policy_id!r} references unknown feedbackEdgeId {edge_id!r}"
                )
            source_type = nodes_by_id.get(edge["source"], {}).get("type")
            if source_type not in ("review.intent", "human.checkpoint"):
                raise ValueError(
                    f"LoopPolicy {policy_id!r} feedback edge {edge_id!r} has source type "
                    f"{source_type!r}, which does not support loop guards "
                    "(v1 supports review.intent/human.checkpoint only)"
                )
            feedback_edges.append(edge)

        targets = {e["target"] for e in feedback_edges}
        if len(targets) != 1:
            raise ValueError(
                f"LoopPolicy {policy_id!r} feedbackEdgeIds must share a single re-entry "
                f"target, got {sorted(targets)!r}"
            )
        continue_target = targets.pop()

        exit_target: str | None = None
        if policy["exitEdgeIds"]:
            exit_edge_id = policy["exitEdgeIds"][0]
            exit_edge = edges_by_id.get(exit_edge_id)
            if exit_edge is None:
                raise ValueError(
                    f"LoopPolicy {policy_id!r} references unknown exitEdgeId {exit_edge_id!r}"
                )
            exit_target = exit_edge["target"]
        if policy["onExhaustion"] in ("exit", "escalate") and exit_target is None:
            raise ValueError(
                f"LoopPolicy {policy_id!r} onExhaustion={policy['onExhaustion']!r} "
                "requires a non-empty exitEdgeIds"
            )

        for edge in feedback_edges:
            edge_target_override[edge["id"]] = guard_node_id

        for member_id in policy["memberNodeIds"]:
            node_to_policies.setdefault(member_id, []).append(policy_id)

        guard_specs.append(
            {
                "policy": policy,
                "guard_node_id": guard_node_id,
                "continue_target": continue_target,
                "exit_target": exit_target,
            }
        )

    return edge_target_override, guard_specs, node_to_policies


def _make_loop_guard_node(
    policy: dict,
    continue_target: str,
    exit_target: str | None,
    emit: EventEmitter,
    run_id: str,
):
    policy_id = policy["id"]
    guard_node_id = f"__loop_guard__{policy_id}"
    on_exhaustion = policy["onExhaustion"]
    max_iterations = (policy.get("guard") or {}).get("maxIterations")

    async def loop_guard(state: AgentState) -> Command:
        await emit(make_event(run_id, guard_node_id, "node_start"))

        prior = (state.get("loop_runtime") or {}).get(policy_id)
        runtime = next_runtime(prior)
        result = evaluate_loop_guard(policy, runtime)
        update = {"iteration": runtime["iteration"], "started_at": runtime["started_at"]}

        loop_runtime_event: dict = {
            "loopPolicyId": policy_id,
            "iteration": runtime["iteration"],
            "tokens": runtime["total_tokens"],
            "costUsd": runtime["total_cost_usd"],
            "durationMs": int((time.time() - runtime["started_at"]) * 1000),
        }
        if max_iterations is not None:
            loop_runtime_event["maxIterations"] = max_iterations
        if runtime["last_feedback"] is not None:
            loop_runtime_event["lastFeedback"] = runtime["last_feedback"]
        if not result["should_continue"]:
            loop_runtime_event["exitReason"] = result["exit_reason"]
        await emit(make_event(run_id, guard_node_id, "node_end", loop_runtime=loop_runtime_event))

        if result["should_continue"]:
            return Command(goto=continue_target, update={"loop_runtime": {policy_id: update}})

        if on_exhaustion == "fail":
            raise RuntimeError(
                f"LoopPolicy {policy_id!r} exhausted ({result['exit_reason']}) "
                "with onExhaustion='fail'"
            )
        return Command(goto=exit_target, update={"loop_runtime": {policy_id: update}})

    return loop_guard
```

- [ ] **Step 4: Wire it into `compile_graph`**

In `compile_graph`, after the existing `outgoing`/`incoming` construction loop and before `graph = StateGraph(AgentState)`, add:

```python
    nodes_by_id = {n["id"]: n for n in nodes}
    edges_by_id = {e["id"]: e for e in edges}
    loop_policies: list[dict] = architecture.get("loopPolicies") or []
    edge_target_override, guard_specs, node_to_policies = _prepare_loop_policies(
        loop_policies, nodes_by_id, edges_by_id
    )
```

Right after `graph = StateGraph(AgentState)` / `route_fns: dict[str, Any] = {}`, add:

```python
    for spec in guard_specs:
        graph.add_node(
            spec["guard_node_id"],
            _make_loop_guard_node(
                spec["policy"], spec["continue_target"], spec["exit_target"], emit, run_id
            ),
        )
```

In the node-registration loop, change the `human.checkpoint` branch's routes construction from:

```python
            routes.update({e["sourceHandle"]: e["target"] for e in outgoing.get(node_id, [])})
```

to:

```python
            routes.update(
                {
                    e["sourceHandle"]: edge_target_override.get(e["id"], e["target"])
                    for e in outgoing.get(node_id, [])
                }
            )
```

In the edge-wiring loop, change the `review.intent` branch from:

```python
        if node_type == "review.intent":
            mapping = {e["sourceHandle"]: e["target"] for e in outs}
            graph.add_conditional_edges(node_id, route_fns[node_id], mapping)
            continue
```

to:

```python
        if node_type == "review.intent":
            mapping = {
                e["sourceHandle"]: edge_target_override.get(e["id"], e["target"]) for e in outs
            }
            graph.add_conditional_edges(node_id, route_fns[node_id], mapping)
            continue
```

(Task 6 will thread `node_to_policies` into `_make_llm_step_node`/`_make_review_node` — leave those two call sites unchanged for now; they still work with their current signatures.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k loop_policy -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full `test_compile.py` suite to check for regressions**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -v`
Expected: PASS — all pre-existing tests (including `test_review_refine_loop_then_accept`) still pass unchanged, since they never set `loopPolicies`.

- [ ] **Step 7: Write the failing end-to-end guard tests**

Add to `server/tests/test_compile.py`:

```python
async def test_loop_policy_max_iterations_trips_to_exit(monkeypatch):
    """LoopPolicy.guard.maxIterations 트립 시 review->refine 루프가 exitEdgeIds로 빠진다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    async def always_unmet(state, *, node_id, **kwargs):
        return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])

    monkeypatch.setattr(review_mod, "run_llm_step", always_unmet)
    emitter = ListEventEmitter()
    refine_edge = _edge("review", "reasoning", "refine")
    accept_edge = _edge("review", "output", "accept")
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", {"maxRetries": 10}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            refine_edge,
            accept_edge,
        ],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            exitEdgeIds=[accept_edge["id"]],
            guard={"maxIterations": 2},
        )
    ]
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-1"}},
    )

    # review 자체 maxRetries=10이라 review는 계속 refine을 원하지만, LoopPolicy의
    # maxIterations=2가 먼저 트립돼 3번째 refine 시도에서 output으로 강제 이탈한다.
    assert final["answer"] == "4"
    guard_events = [
        e for e in emitter.events if e.node_id == "__loop_guard__loop-1" and e.loop_runtime
    ]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2, 3]
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"


async def test_loop_policy_on_exhaustion_fail_raises(monkeypatch):
    """onExhaustion='fail'이 트립되면 런타임 예외가 발생한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    async def always_unmet(state, *, node_id, **kwargs):
        return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])

    monkeypatch.setattr(review_mod, "run_llm_step", always_unmet)
    emitter = ListEventEmitter()
    refine_edge = _edge("review", "reasoning", "refine")
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", {"maxRetries": 10}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            refine_edge,
            _edge("review", "output", "accept"),
        ],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            guard={"maxIterations": 1},
            onExhaustion="fail",
        )
    ]
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    with pytest.raises(RuntimeError, match="onExhaustion='fail'"):
        await graph.ainvoke(
            initial_state("", criteria=criteria, intent="정확한 계산"),
            {"configurable": {"thread_id": "t-loop-fail"}},
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -v`
Expected: PASS (all tests, pre-existing + new)

- [ ] **Step 9: Lint and full backend suite**

Run: `cd server && ../server/.venv/bin/ruff check . && ../server/.venv/bin/ruff format --check . && ../server/.venv/bin/python -m pytest`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "feat(server): wire LoopPolicy into compile_graph via a synthetic guard node"
```

---

### Task 6: Backend — token/cost budget plumbing

**Files:**
- Modify: `server/nodes/llm_step.py`
- Modify: `server/nodes/review.py`
- Modify: `server/graphs/compile.py`
- Test: `server/tests/test_llm_step_policy.py` (extend)
- Test: `server/tests/test_compile.py` (extend)

**Interfaces:**
- Consumes: `node_to_policies` (Task 5, from `_prepare_loop_policies`), `merge_loop_runtime`'s sum semantics (Task 2).
- Produces: `run_llm_step(..., usage_sink: dict | None = None)` — when given, populated with `{"prompt": int, "completion": int, "cost": float}` on any successful call (primary or fallback). `_emit_token_usage(..., usage_sink: dict | None = None)`. `make_review(..., loop_policy_ids: list[str] | None = None)`. `_make_llm_step_node(..., loop_policy_ids: list[str] | None = None)`, `_make_review_node(..., loop_policy_ids: list[str] | None = None)`.

- [ ] **Step 1: Write the failing `_emit_token_usage` tests**

Add to `server/tests/test_llm_step_policy.py` (add `from nodes import llm_step as llm_mod` is already imported at the top — reuse it):

```python
async def test_emit_token_usage_populates_usage_sink():
    """usage_cb.usage_metadata가 있으면 usage_sink에 prompt/completion/cost를 채운다."""

    class FakeUsageCallback:
        usage_metadata = {"claude-3": {"input_tokens": 100, "output_tokens": 50}}

    emit = ListEventEmitter()
    usage: dict = {}
    await llm_mod._emit_token_usage(
        FakeUsageCallback(),
        emit=emit,
        run_id="r",
        node_id="n",
        model_name="claude-3",
        usage_sink=usage,
    )
    assert usage["prompt"] == 100
    assert usage["completion"] == 50
    assert usage["cost"] >= 0
    assert any(e.event_type == "log" and e.token_usage for e in emit.events)


async def test_emit_token_usage_without_sink_still_emits_log():
    """usage_sink가 None이어도 기존 log 이벤트 방출은 그대로 유지된다(회귀)."""

    class FakeUsageCallback:
        usage_metadata = {"claude-3": {"input_tokens": 10, "output_tokens": 5}}

    emit = ListEventEmitter()
    await llm_mod._emit_token_usage(
        FakeUsageCallback(), emit=emit, run_id="r", node_id="n", model_name="claude-3"
    )
    assert any(e.event_type == "log" and e.token_usage for e in emit.events)
```

Also add `from events import ListEventEmitter` if not already imported at module scope (check the existing import block — `from events import ListEventEmitter` is already there).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_llm_step_policy.py -k usage_sink -v`
Expected: FAIL — `TypeError: _emit_token_usage() got an unexpected keyword argument 'usage_sink'`.

- [ ] **Step 3: Add `usage_sink` to `server/nodes/llm_step.py`**

Change `run_llm_step`'s signature (add after `call_policy: CallPolicy | None = None,`):

```python
    usage_sink: dict | None = None,
```

Update both call sites of `_emit_token_usage` inside `run_llm_step` (primary success path and fallback success path) to pass `usage_sink=usage_sink`:

```python
            await _emit_token_usage(
                usage_cb,
                emit=emit,
                run_id=run_id,
                node_id=node_id,
                model_name=used_model_name,
                attempt=attempt,
                fallback_used=False,
                usage_sink=usage_sink,
            )
```

```python
            await _emit_token_usage(
                usage_cb,
                emit=emit,
                run_id=run_id,
                node_id=node_id,
                model_name=used_model_name,
                attempt=0,
                fallback_used=True,
                usage_sink=usage_sink,
            )
```

Change `_emit_token_usage`'s signature (add after `fallback_used: bool = False,`):

```python
    usage_sink: dict | None = None,
```

Inside `_emit_token_usage`, right after the `if prompt == 0 and completion == 0: return` guard, add:

```python
    if usage_sink is not None:
        usage_sink["prompt"] = prompt
        usage_sink["completion"] = completion
        usage_sink["cost"] = cost
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_llm_step_policy.py -v`
Expected: PASS (all tests — the 5 pre-existing ones untouched, since `usage_sink` defaults to `None` and none of them pass it; plus the 2 new ones)

- [ ] **Step 5: Thread `loop_policy_ids` through `make_review`**

In `server/nodes/review.py`, change `make_review`'s signature (add after `call_policy: CallPolicy | None = None,`):

```python
    loop_policy_ids: list[str] | None = None,
```

Right after `escalate = ESCALATE_TAGS if escalate_tags is None else escalate_tags`, add:

```python
    policy_ids = loop_policy_ids or []
```

Change the internal `run_llm_step` call to capture usage:

```python
        probe: AgentState = {**state, "criteria": criteria}  # type: ignore[typeddict-item]
        usage: dict = {}
        delta = await run_llm_step(
            probe,
            node_id=node_id,
            system_prompt=REVIEW_SYSTEM_PROMPT,
            input_keys=[
                ("task", "Task"),
                ("intent", "Intent"),
                ("criteria", "Acceptance Criteria"),
                ("answer", "Answer"),
            ],
            output_model=ReviewDelta,
            model=model,
            emit=emit,
            run_id=run_id,
            call_policy=call_policy,
            usage_sink=usage,
        )
```

Right after the existing `if branch == "refine": ...` block that builds `updates`, add the budget contribution:

```python
        if policy_ids and usage:
            updates["loop_runtime"] = {
                pid: {
                    "total_tokens": usage.get("prompt", 0) + usage.get("completion", 0),
                    "total_cost_usd": usage.get("cost", 0.0),
                }
                for pid in policy_ids
            }
```

(This sits between the existing `if branch == "refine":` block and the `unmet = sum(...)` line that computes the log `reason` string — order doesn't matter since they touch different dict keys.)

- [ ] **Step 6: Thread `loop_policy_ids` through `_make_review_node` and `_make_llm_step_node`, and pass `node_to_policies` at the call sites**

In `server/graphs/compile.py`, change `_make_review_node`'s signature and pass-through:

```python
def _make_review_node(
    node: dict,
    model,
    policy: CallPolicy,
    emit: EventEmitter,
    run_id: str,
    loop_policy_ids: list[str] | None = None,
):
    node_cfg = node.get("config") or {}
    seed_criteria = [
        Criterion(id=f"cfg-{i + 1}", text=text).model_dump()
        for i, text in enumerate(node_cfg.get("criteria") or [])
        if isinstance(text, str) and text.strip()
    ]
    return make_review(
        model=model,
        emit=emit,
        run_id=run_id,
        node_id=node["id"],
        max_retries=int(node_cfg.get("maxRetries", config.MAX_RETRIES)),
        escalate_tags=set(node_cfg.get("escalateTags") or config.ESCALATE_TAGS),
        seed_criteria=seed_criteria,
        call_policy=policy,
        loop_policy_ids=loop_policy_ids,
    )
```

Change `_make_llm_step_node`'s signature and body:

```python
def _make_llm_step_node(
    node: dict,
    manifest: dict,
    model,
    policy: CallPolicy,
    emit: EventEmitter,
    run_id: str,
    loop_policy_ids: list[str] | None = None,
):
    node_id = node["id"]
    node_type = node["type"]
    spec = LLM_STEP_TABLE[node_type]
    system_prompt = (node.get("config") or {}).get("systemPrompt") or manifest.get(
        "defaults", {}
    ).get("systemPrompt", "")
    input_keys = [(p["id"], p["label"]) for p in manifest["inputs"]] + spec["extra_inputs"]
    policy_ids = loop_policy_ids or []

    async def step(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        usage: dict = {}
        result = await run_llm_step(
            state,
            node_id=node_id,
            system_prompt=system_prompt,
            input_keys=input_keys,
            output_model=spec["output_model"],
            model=model,
            emit=emit,
            run_id=run_id,
            call_policy=policy,
            usage_sink=usage,
        )
        updates = spec["to_updates"](result, state)
        if policy_ids and usage:
            updates["loop_runtime"] = {
                pid: {
                    "total_tokens": usage.get("prompt", 0) + usage.get("completion", 0),
                    "total_cost_usd": usage.get("cost", 0.0),
                }
                for pid in policy_ids
            }
        await emit(make_event(run_id, node_id, "node_end", output=spec["to_event_output"](result)))
        return updates

    return step
```

Finally, update the two call sites in `compile_graph`'s node-registration loop to pass `node_to_policies.get(node_id)`:

```python
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
                _make_review_node(
                    node, model, policy, emit, run_id, node_to_policies.get(node_id)
                ),
            )
```

- [ ] **Step 7: Run the full backend suite to check for regressions**

Run: `cd server && ../server/.venv/bin/python -m pytest`
Expected: PASS — `baseline.py`/`treatment.py`/`classify.py` never pass `usage_sink`/`loop_policy_ids`, so their behavior (and `test_graph_baseline.py`/`test_graph_treatment.py`) is unaffected.

- [ ] **Step 8: Write the failing end-to-end budget test**

Add to `server/tests/test_compile.py`:

```python
async def test_loop_policy_max_tokens_trips_to_exit(monkeypatch):
    """루프 멤버 노드가 보고한 토큰이 누적돼 maxTokens 가드를 트립시킨다."""
    _patch_model(monkeypatch)

    async def reasoning_with_usage(state, *, node_id, usage_sink=None, **kwargs):
        if usage_sink is not None:
            usage_sink["prompt"] = 400
            usage_sink["completion"] = 200
            usage_sink["cost"] = 0.02
        return {"answer": "4", "confidence": 0.9}

    async def review_always_unmet(state, *, node_id, usage_sink=None, **kwargs):
        return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])

    monkeypatch.setattr(compile_mod, "run_llm_step", reasoning_with_usage)
    monkeypatch.setattr(review_mod, "run_llm_step", review_always_unmet)

    emitter = ListEventEmitter()
    refine_edge = _edge("review", "reasoning", "refine")
    accept_edge = _edge("review", "output", "accept")
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", {"maxRetries": 10}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            refine_edge,
            accept_edge,
        ],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            exitEdgeIds=[accept_edge["id"]],
            guard={"maxTokens": 1000},
        )
    ]
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-tokens"}},
    )

    # reasoning이 매 패스 600토큰(400+200)씩 보고 — 2번째 refine 진입 시 1200 > 1000으로 트립.
    assert final["answer"] == "4"
    guard_events = [
        e for e in emitter.events if e.node_id == "__loop_guard__loop-1" and e.loop_runtime
    ]
    assert guard_events[-1].loop_runtime["exitReason"] == "budget"
    assert guard_events[-1].loop_runtime["tokens"] >= 1000
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k max_tokens -v`
Expected: PASS

- [ ] **Step 10: Full backend suite + lint**

Run: `cd server && ../server/.venv/bin/ruff check . && ../server/.venv/bin/ruff format --check . && ../server/.venv/bin/python -m pytest`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add server/nodes/llm_step.py server/nodes/review.py server/graphs/compile.py server/tests/test_llm_step_policy.py server/tests/test_compile.py
git commit -m "feat(server): surface token/cost usage into loop_runtime for budget guards"
```

---

### Task 7: Backend — stuck detection (progress signal)

**Files:**
- Modify: `server/nodes/review.py`
- Test: `server/tests/test_compile.py` (extend)

**Interfaces:**
- Consumes: `policy_ids`/`usage` construction from Task 6 (extends the same code region in `review.py`).
- Produces: `review()`'s `updates["loop_runtime"]` now also carries `progress_history` (a 1-element list: the unmet must-pass-or-any count for this pass) and `last_feedback`.

- [ ] **Step 1: Write the failing end-to-end stuck test**

Add to `server/tests/test_compile.py`:

```python
async def test_loop_policy_stuck_trips_to_exit(monkeypatch):
    """review가 보고하는 unmet 개수가 stuck window 동안 개선되지 않으면 stuck으로 트립된다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    async def review_always_two_unmet(state, *, node_id, usage_sink=None, **kwargs):
        return _delta(
            [
                {"id": "c1", "verdict": "unmet", "evidence": "부족"},
                {"id": "c2", "verdict": "unmet", "evidence": "부족"},
            ]
        )

    monkeypatch.setattr(review_mod, "run_llm_step", review_always_two_unmet)
    emitter = ListEventEmitter()
    refine_edge = _edge("review", "reasoning", "refine")
    accept_edge = _edge("review", "output", "accept")
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent", {"maxRetries": 10}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            refine_edge,
            accept_edge,
        ],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            exitEdgeIds=[accept_edge["id"]],
            guard={"stuck": {"window": 2, "threshold": 1}},
        )
    ]
    criteria = [
        {"id": "c1", "text": "정답 포함", "severity": "must_pass"},
        {"id": "c2", "text": "풀이 포함", "severity": "must_pass"},
    ]
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-loop-stuck"}},
    )

    assert final["answer"] == "4"
    guard_events = [
        e for e in emitter.events if e.node_id == "__loop_guard__loop-1" and e.loop_runtime
    ]
    assert guard_events[-1].loop_runtime["exitReason"] == "stuck"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k stuck -v`
Expected: FAIL — `guard_events[-1].loop_runtime["exitReason"]` is missing/not `"stuck"` because `progress_history` is never populated (the guard always sees an empty history, `_is_stuck` always returns `False` since `len(progress_history) < window`).

- [ ] **Step 3: Extend the `loop_runtime` contribution in `server/nodes/review.py`**

Replace the block added in Task 6 Step 5 (`if policy_ids and usage: ...`) with:

```python
        if policy_ids:
            unmet_count = sum(
                1 for v in delta.get("per_criterion") or [] if v.get("verdict") == "unmet"
            )
            contribution: dict = {"progress_history": [float(unmet_count)]}
            if usage:
                contribution["total_tokens"] = usage.get("prompt", 0) + usage.get("completion", 0)
                contribution["total_cost_usd"] = usage.get("cost", 0.0)
            if updates.get("feedback") is not None:
                contribution["last_feedback"] = updates["feedback"]
            updates["loop_runtime"] = {pid: contribution for pid in policy_ids}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k stuck -v`
Expected: PASS

- [ ] **Step 5: Full backend suite + lint**

Run: `cd server && ../server/.venv/bin/ruff check . && ../server/.venv/bin/ruff format --check . && ../server/.venv/bin/python -m pytest`
Expected: PASS — including the maxTokens test from Task 6 (its `review_always_unmet` fake doesn't set `usage_sink`, so `usage` stays empty there and `contribution` in that test only carries `progress_history` — the assertion in that test only checks `tokens`/`exitReason` on the guard's own accumulated `runtime`, which still comes from `reasoning`'s contribution, so it's unaffected).

- [ ] **Step 6: Commit**

```bash
git add server/nodes/review.py server/tests/test_compile.py
git commit -m "feat(server): report review's unmet-count progress signal for stuck detection"
```

---

### Task 8: Migration regression test + full verification

**Files:**
- Test: `server/tests/test_compile.py` (extend)

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: no new production code — final regression coverage and a full clean-suite verification.

- [ ] **Step 1: Write the migration regression test**

Add to `server/tests/test_compile.py`:

```python
async def test_architecture_without_loop_policies_key_behaves_unchanged(monkeypatch):
    """loopPolicies 키 자체가 없는(기존 저장 파일 형태) Architecture는 예전 그대로 동작한다."""
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
    # loopPolicies 키를 아예 넣지 않는다 — architecture.get("loopPolicies") or [] 폴백 경로 검증.
    arch = {
        "version": "1",
        "metadata": {"name": "legacy"},
        "nodes": [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        "edges": [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "reasoning", "refine"),
            _edge("review", "output", "accept"),
        ],
    }
    assert "loopPolicies" not in arch

    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t-legacy"}},
    )

    assert final["review_branch"] == "accept"
    assert final["retries"] == 1
    # 가드 노드가 전혀 등록되지 않았으므로 __loop_guard__ 이벤트도 없다.
    assert not any(e.node_id.startswith("__loop_guard__") for e in emitter.events)
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd server && ../server/.venv/bin/python -m pytest tests/test_compile.py -k legacy -v`
Expected: PASS (this should already pass without any production code change, since Tasks 1–7 were built to be additive — this step is a proof, not a fix)

- [ ] **Step 3: Full backend verification**

Run:
```bash
cd server
../server/.venv/bin/ruff check .
../server/.venv/bin/ruff format --check .
../server/.venv/bin/python -m pytest -v
```
Expected: PASS, zero failures, zero lint/format issues.

- [ ] **Step 4: Full frontend verification**

Run:
```bash
cd ui
npm run lint
npm run build
npm run test
```
Expected: PASS, zero failures. `npm run build` (not just `tsc --noEmit`) is required — `tsc -b` has caught type errors in this project that `--noEmit` missed (see `CLAUDE.local.md`).

- [ ] **Step 5: Commit**

```bash
git add server/tests/test_compile.py
git commit -m "test(server): add migration regression test for policy-less Architectures"
```

---

## Post-plan follow-ups (not part of this plan)

- `recursion_limit` (`cfg.MAX_RETRIES * 10 + 20` in `server/main.py`) should be revisited once real `LoopPolicy.guard.maxIterations` values are in use, so the global safety cap comfortably exceeds the sum of configured policies' budgets plus their guard-node hops.
- The Loop Lens policy-editing UI and Loops-panel rendering of `loopRuntime` are separate follow-on work (spec's Remaining Work #5) — not part of this plan.
- `docs/superpowers/specs/2026-08-06-loop-policy-design.md`'s "확장 지점" section documents how to add new guard axes or new loop kinds after this plan lands.
