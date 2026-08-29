> 📄 **완료된 작업 기록** — 당시 구현 계획서다. 현재 설계 문서가 아니며, 현재 방향은 [DIRECTION.md](../../../DIRECTION.md) 참고.

# Freeform Connections — Phase A1 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `server/graphs/compile.py` accept freeform, role-on-edge canvas connections — resolving a branch edge's role from `sourceRole` (falling back to `sourceHandle` for old saved architectures), validating that role assignment before compiling, adding a required-input existence check, and compiling declared AND-joins into real LangGraph join-edges — with zero frontend changes required to land this task.

**Architecture:** Every change lives in `server/graphs/compile.py` plus its test file. Four small, independently-testable pieces get added in sequence: a role-resolution helper that both old and new edge shapes flow through, a generalized branch-role validator that replaces the loop-guard-only one, a graph-wide required-input existence check, and a pure function that decides — per target node — whether incoming plain edges become one `add_edge([sources], target)` join or individual `add_edge(source, target)` calls. Nothing in this plan touches the frontend; the backend will correctly handle `sourceRole`/`joinMode` fields the moment the frontend starts sending them, and continues to compile every architecture saved before this change with zero migration.

**Tech Stack:** Python 3.12, LangGraph 1.2.10 (installed; `pyproject.toml` only pins `>=0.2.0` as a floor), pytest + pytest-asyncio, ruff.

**Spec:** `docs/superpowers/specs/2026-08-16-freeform-connections-node-templates-design.md` — this plan implements §1 (role resolution), §4 (AND/OR join), §5 (backend validators), and the Tier 1 half of §6 (required-input validator).

## Global Constraints

- Python 3.12, run everything through `server/.venv/bin/python` / `server/.venv/bin/pytest` / `server/.venv/bin/ruff` — never a bare `python`/`pytest`/`ruff`.
- `ruff check .` then `ruff format .` in `server/` must be clean before any commit (AGENTS.md §2). Line length 100 (`pyproject.toml`).
- Never mock away real behavior to make a test pass — external LLM calls are mocked (AGENTS.md §6), everything else runs for real (real `compile_graph`, real `StateGraph`, real `ainvoke`).
- Always use absolute paths in file references and tool calls (AGENTS.md §1).
- No frontend changes in this plan — `ui/` is out of scope. The follow-up frontend plan depends on the field names introduced here (`sourceRole` on edges, `joinMode` on nodes) matching exactly.
- Every new test lives in `server/tests/test_compile.py`, following the existing helpers (`_arch`, `_node`, `_edge`, `_patch_model`, `ListEventEmitter`, `initial_state`) — don't invent parallel helpers.

---

### Task 1: `_resolved_role` — the migration-free role fallback

**Files:**
- Modify: `server/graphs/compile.py:287-289` (`_handle_targets`)
- Modify: `server/tests/test_compile.py:23-30` (`_edge()` helper)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Produces: `_resolved_role(edge: dict) -> str` — every later task in this plan calls this instead of reading `edge["sourceHandle"]` directly.
- Produces: `_edge(source, target, source_handle="out", target_handle="in", source_role=None) -> dict` — every new test in this plan that needs an "unassigned" or freeform edge uses this new `source_role` parameter.

- [ ] **Step 1: Add the `source_role` parameter to the `_edge()` test helper**

Edit `server/tests/test_compile.py`, replacing the existing `_edge` function (lines 23-30):

```python
def _edge(source, target, source_handle="out", target_handle="in", source_role=None):
    edge = {
        "id": f"e-{source}-{target}",
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }
    if source_role is not None:
        edge["sourceRole"] = source_role
    return edge
```

This is backward compatible — every existing call site (`_edge("input", "reasoning", "task")` etc.) keeps working unchanged, since `source_role` defaults to `None` and the key is only added when explicitly passed.

- [ ] **Step 2: Write the failing tests for `_resolved_role`**

Add to `server/tests/test_compile.py`, right after the `_delta` helper (after line 40):

```python
def test_resolved_role_prefers_source_role_over_handle():
    """새로 그은 프리폼 엣지는 sourceHandle이 의미 없는 내부 id이므로 sourceRole을 쓴다."""
    edge = _edge("a", "b", source_handle="opaque-1", source_role="accept")
    assert compile_mod._resolved_role(edge) == "accept"


def test_resolved_role_falls_back_to_source_handle_when_no_role():
    """기존 저장된 아키텍처는 sourceRole이 없고 sourceHandle 자체가 이미 역할 이름이다."""
    edge = _edge("a", "b", source_handle="accept")
    assert compile_mod._resolved_role(edge) == "accept"


def test_handle_targets_resolves_via_source_role():
    outgoing = {
        "review": [_edge("review", "output", source_handle="opaque-1", source_role="accept")]
    }
    assert compile_mod._handle_targets(outgoing, "review") == {"accept": "output"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "resolved_role or handle_targets_resolves" -v`
Expected: FAIL with `AttributeError: module 'graphs.compile' has no attribute '_resolved_role'`

- [ ] **Step 4: Implement `_resolved_role` and migrate `_handle_targets`**

In `server/graphs/compile.py`, insert this new function immediately before `_handle_targets` (before line 287):

```python
def _resolved_role(edge: dict) -> str:
    """엣지의 최종 역할 문자열. 프리폼 캔버스가 그리는 새 엣지는 sourceHandle이
    의미 없는 내부 id이고 Inspector가 채운 sourceRole만 진짜 역할이다. 기존에
    저장된 아키텍처는 sourceRole이 없고 sourceHandle 자체가 이미 역할 이름이므로
    (예: "accept") 그대로 쓴다 — 이 폴백이 마이그레이션을 공짜로 만든다
    (설계 §1)."""
    return edge.get("sourceRole") or edge["sourceHandle"]
```

Then replace `_handle_targets` (lines 287-289) with:

```python
def _handle_targets(outgoing: dict[str, list[dict]], node_id: str) -> dict[str, str]:
    """노드의 outgoing 엣지를 역할(resolved role) → target 으로 인덱싱한다."""
    return {_resolved_role(e): e["target"] for e in outgoing.get(node_id, [])}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -v`
Expected: all tests PASS (the full file, not just the new ones — this confirms the `_handle_targets` change doesn't regress any existing caller).

- [ ] **Step 6: Lint and commit**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .`

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "$(cat <<'EOF'
feat(compile): resolve edge role from sourceRole, falling back to sourceHandle

Introduces _resolved_role as the single place that reads a branch
edge's role, so freeform canvas edges (opaque sourceHandle + explicit
sourceRole from Inspector) and every previously-saved architecture
(sourceHandle already equals the role name) both resolve correctly
with no migration.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

---

### Task 2: `_validate_branch_roles` — replaces the loop-guard-only validator

**Files:**
- Modify: `server/graphs/compile.py:292-305` (replace `_validate_loop_guard_ports`)
- Modify: `server/graphs/compile.py:532-549` (wire the new validator into all three branch-runtime node types)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Consumes: `_resolved_role(edge: dict) -> str` (Task 1).
- Produces: `_validate_branch_roles(node_id: str, manifest: dict, outs: list[dict]) -> None` — raises `ValueError` on an unassigned/unknown role or a duplicate role assignment; returns `None` otherwise. Called for `review.intent`, `human.checkpoint`, and `loop.guard` nodes.

- [ ] **Step 1: Write the failing unit tests**

Add to `server/tests/test_compile.py`, after the three tests added in Task 1:

```python
def test_validate_branch_roles_raises_for_unassigned_role():
    """프리폼으로 그었지만 아직 Inspector에서 역할을 안 고른 엣지 — sourceRole 없음,
    opaque sourceHandle이라 유효한 역할 이름이 아니다."""
    manifest = compile_mod.MANIFESTS_BY_TYPE["review.intent"]
    outs = [_edge("review", "output", source_handle="opaque-1")]
    with pytest.raises(ValueError, match="unassigned or unknown"):
        compile_mod._validate_branch_roles("review", manifest, outs)


def test_validate_branch_roles_accepts_freeform_edge_with_source_role():
    manifest = compile_mod.MANIFESTS_BY_TYPE["review.intent"]
    outs = [_edge("review", "output", source_handle="opaque-1", source_role="accept")]
    compile_mod._validate_branch_roles("review", manifest, outs)  # 예외 없이 통과해야 함


def test_validate_branch_roles_raises_for_duplicate_role():
    manifest = compile_mod.MANIFESTS_BY_TYPE["review.intent"]
    outs = [
        _edge("review", "a", source_handle="refine"),
        _edge("review", "b", source_handle="opaque-2", source_role="refine"),
    ]
    with pytest.raises(ValueError, match=r"2 edges assigned the 'refine' role"):
        compile_mod._validate_branch_roles("review", manifest, outs)


def test_validate_branch_roles_accepts_distinct_roles():
    manifest = compile_mod.MANIFESTS_BY_TYPE["review.intent"]
    outs = [
        _edge("review", "a", source_handle="accept"),
        _edge("review", "b", source_handle="refine"),
    ]
    compile_mod._validate_branch_roles("review", manifest, outs)  # 예외 없이 통과해야 함


def test_validate_branch_roles_accepts_empty_outs():
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    compile_mod._validate_branch_roles("checkpoint", manifest, [])  # 예외 없이 통과해야 함
```

Also update the two existing loop-guard fanout tests to expect the new, generalized error message. In `server/tests/test_compile.py`:

Replace (around line 600):
```python
    with pytest.raises(ValueError, match=r"2 edges on its 'loopBack' port"):
```
with:
```python
    with pytest.raises(ValueError, match=r"2 edges assigned the 'loopBack' role"):
```

Replace (around line 626):
```python
    with pytest.raises(ValueError, match=r"2 edges on its 'exit' port"):
```
with:
```python
    with pytest.raises(ValueError, match=r"2 edges assigned the 'exit' role"):
```

Finally, add one full-compile integration test proving the validator is actually wired into `compile_graph` for `review.intent` (not just callable in isolation):

```python
async def test_review_unassigned_branch_edge_raises_at_compile(monkeypatch):
    """프리폼으로 그은 뒤 아직 Inspector에서 역할을 안 고른 엣지는 컴파일 타임에 막혀야
    한다 — 지금까지는 review 노드가 런타임에 ValueError로 죽거나(review)
    human.checkpoint처럼 조용히 END로 빠지는 문제였다."""
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
            _edge("review", "output", source_handle="opaque-slot-1"),  # 역할 미배정
        ],
    )
    with pytest.raises(ValueError, match="unassigned or unknown"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "validate_branch_roles or unassigned_branch_edge" -v`
Expected: FAIL — `_validate_branch_roles` doesn't exist yet.

- [ ] **Step 3: Implement `_validate_branch_roles`, replacing `_validate_loop_guard_ports`**

In `server/graphs/compile.py`, replace `_validate_loop_guard_ports` (lines 292-305) entirely with:

```python
def _validate_branch_roles(node_id: str, manifest: dict, outs: list[dict]) -> None:
    """분기 런타임 노드(review.intent/loop.guard/human.checkpoint)의 나가는 엣지마다,
    resolved role(_resolved_role)이 매니페스트가 선언한 출력 역할 중 하나인지, 그리고
    같은 역할이 두 번 배정되지 않았는지 검증한다 (설계 §5).

    - 알 수 없는/미배정 역할: 프리폼 엣지를 그었지만 Inspector에서 역할을 아직
      고르지 않은 상태. _handle_targets가 조용히 무시하거나(loop.guard) 런타임에
      ValueError로 죽는(review) 상황을 컴파일 타임에 미리 막는다.
    - 중복 배정: _handle_targets가 dict라 나중 엣지가 앞의 걸 조용히 덮어쓴다 —
      기존에 loop.guard의 loopBack/exit 포트만 막던 걸 review/checkpoint를 포함해
      모든 분기 런타임 노드로 일반화한다.
    """
    valid_roles = {p["id"] for p in manifest["outputs"]}
    role_counts: dict[str, int] = {}
    for e in outs:
        role = _resolved_role(e)
        if role not in valid_roles:
            raise ValueError(
                f"node {node_id!r} has an outgoing edge with an unassigned or unknown "
                f"role {role!r} — assign one of {sorted(valid_roles)} in Inspector"
            )
        role_counts[role] = role_counts.get(role, 0) + 1
    for role, count in role_counts.items():
        if count > 1:
            raise ValueError(
                f"node {node_id!r} has {count} edges assigned the {role!r} role — "
                "each role must have exactly one outgoing edge"
            )
```

- [ ] **Step 4: Wire the validator into all three branch-runtime node types**

In `server/graphs/compile.py`, in `compile_graph`'s node-creation loop, make three edits:

Replace the `review.intent` branch (lines 532-539):
```python
        elif node_type == "review.intent":
            model, policy = _resolve_model(node, default_model_cfg)
            wired = set(_handle_targets(outgoing, node_id))
            route_fns[node_id] = make_route_review(wired)
            graph.add_node(
                node_id,
                _make_review_node(node, model, policy, emit, run_id, node_to_policies.get(node_id)),
            )
```
with:
```python
        elif node_type == "review.intent":
            _validate_branch_roles(node_id, manifest, outgoing.get(node_id, []))
            model, policy = _resolve_model(node, default_model_cfg)
            wired = set(_handle_targets(outgoing, node_id))
            route_fns[node_id] = make_route_review(wired)
            graph.add_node(
                node_id,
                _make_review_node(node, model, policy, emit, run_id, node_to_policies.get(node_id)),
            )
```

Replace the `human.checkpoint` branch (lines 540-546):
```python
        elif node_type == "human.checkpoint":
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update(_handle_targets(outgoing, node_id))
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
```
with:
```python
        elif node_type == "human.checkpoint":
            _validate_branch_roles(node_id, manifest, outgoing.get(node_id, []))
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update(_handle_targets(outgoing, node_id))
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
```

In the `loop.guard` branch, replace the existing call (line 549):
```python
            _validate_loop_guard_ports(node_id, outgoing.get(node_id, []))
```
with:
```python
            _validate_branch_roles(node_id, manifest, outgoing.get(node_id, []))
```

- [ ] **Step 5: Run the full test file to verify everything passes**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -v`
Expected: all tests PASS, including the two updated fanout tests and the new unassigned-role integration test.

- [ ] **Step 6: Lint and commit**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .`

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "$(cat <<'EOF'
feat(compile): generalize branch-role validation beyond loop.guard

_validate_branch_roles replaces _validate_loop_guard_ports, extending
duplicate-role detection to review.intent and human.checkpoint and
adding a new check: every outgoing edge from a branch-runtime node
must resolve to one of the node's declared output roles. Without this,
a freeform edge left unassigned in Inspector either crashes at runtime
(review) or is silently routed to END (human.checkpoint) instead of
failing at compile time.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

---

### Task 3: Tier 1 required-input validator

**Files:**
- Modify: `server/graphs/compile.py:29-48` (`LLM_STEP_TABLE` — add `"writes"` to each entry)
- Modify: `server/graphs/compile.py:483-490` (`compile_graph` — wire in the new validator)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Consumes: `MANIFESTS_BY_TYPE`, `LLM_STEP_TABLE` (existing module-level dicts).
- Produces: `_validate_required_inputs(nodes: list[dict]) -> None` — raises `ValueError` if an `llm_step`-runtime node declares a `required: true` input whose key is neither pre-seeded by `initial_state()` nor written by any `llm_step`-runtime node in the graph.

- [ ] **Step 1: Write the failing tests**

Add to `server/tests/test_compile.py`:

```python
def test_validate_required_inputs_passes_when_preseeded_key_has_no_writer_node():
    """task는 initial_state()가 항상 채우므로, io.input 노드가 그래프에 없어도
    reasoning.cot의 required task는 충족된 것으로 본다 (설계 §6, Tier 1)."""
    nodes = [_node("reasoning", "reasoning.cot"), _node("output", "io.output")]
    compile_mod._validate_required_inputs(nodes)  # 예외 없이 통과해야 함


def test_validate_required_inputs_passes_when_a_writer_exists():
    nodes = [_node("planning", "planning.decompose"), _node("reasoning", "reasoning.cot")]
    compile_mod._validate_required_inputs(nodes)  # 예외 없이 통과해야 함


def test_validate_required_inputs_raises_when_no_node_writes_a_required_non_preseeded_key(
    monkeypatch,
):
    """오늘의 실제 매니페스트는 이 케이스가 없어(모든 required 입력이 preseeded) 합성
    llm_step 타입을 주입해 재현한다."""
    fake_manifest = {
        "type": "test.needs_summary",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Needs Summary",
        "description": "",
        "inputs": [{"id": "summary", "label": "Summary", "dataType": "text", "required": True}],
        "outputs": [],
        "config": [],
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "test.needs_summary", fake_manifest)
    monkeypatch.setitem(
        compile_mod.LLM_STEP_TABLE,
        "test.needs_summary",
        {"output_model": None, "extra_inputs": [], "writes": []},
    )
    nodes = [_node("n1", "test.needs_summary")]
    with pytest.raises(ValueError, match="requires input 'summary'"):
        compile_mod._validate_required_inputs(nodes)


async def test_compile_graph_raises_for_missing_required_input(monkeypatch):
    """_validate_required_inputs가 compile_graph에 실제로 연결돼 있는지 확인 — 노드
    생성/모델 해석보다 먼저 돌아야 실행 비용을 들이기 전에 막는다."""
    fake_manifest = {
        "type": "test.needs_summary",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Needs Summary",
        "description": "",
        "inputs": [{"id": "summary", "label": "Summary", "dataType": "text", "required": True}],
        "outputs": [],
        "config": [],
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "test.needs_summary", fake_manifest)
    monkeypatch.setitem(
        compile_mod.LLM_STEP_TABLE,
        "test.needs_summary",
        {"output_model": None, "extra_inputs": [], "writes": []},
    )
    arch = _arch([_node("n1", "test.needs_summary")], [])
    with pytest.raises(ValueError, match="requires input 'summary'"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, None, "run-1")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "required_input" -v`
Expected: FAIL — `_validate_required_inputs` doesn't exist yet.

- [ ] **Step 3: Add `"writes"` to `LLM_STEP_TABLE`**

In `server/graphs/compile.py`, replace `LLM_STEP_TABLE` (lines 29-48) with:

```python
# type -> (output_model, extra_inputs, to_state_updates, to_event_output)
LLM_STEP_TABLE: dict[str, dict[str, Any]] = {
    "planning.decompose": {
        "output_model": PlanOut,
        "extra_inputs": [],
        "writes": ["plan"],
        "to_updates": lambda result, state: {"plan": result["steps"]},
        "to_event_output": lambda result: {"plan": result["steps"]},
    },
    "reasoning.cot": {
        "output_model": ReasonOut,
        "extra_inputs": [("feedback", "Previous Feedback")],
        "writes": ["answer", "confidence"],
        "to_updates": lambda result, state: {
            "answer": result["answer"],
            "confidence": result["confidence"],
        },
        "to_event_output": lambda result: {
            "answer": result["answer"],
            "confidence": result["confidence"],
        },
    },
}
```

- [ ] **Step 4: Implement `_validate_required_inputs`**

In `server/graphs/compile.py`, add this after `_validate_gated_cycles` (after line 373, before `_derive_loop_members`):

```python
_PRESEEDED_STATE_KEYS = {"task", "task_tags", "intent", "criteria", "batch_mode"}


def _validate_required_inputs(nodes: list[dict]) -> None:
    """llm_step 런타임 노드가 required로 선언한 입력마다, 그 state key를 쓰는 노드가
    그래프 안에 있는지 검사한다 (Tier 1 — may-분석, 사이클/백엣지 구분 없음, 설계 §6).

    llm_step 노드만 대상인 이유: run_llm_step이 manifest["inputs"]를 그대로
    state.get(key)로 읽는 유일한 런타임이다. review/checkpoint/loop_guard는 자기
    코드 안에 고정된 키를 읽거나(make_review) manifest 입력을 아예 안 읽으므로,
    이 노드들의 required 플래그를 검사하면 실제로 존재하지 않는 state key(예:
    io.output의 "result")까지 필수로 취급해 정상 그래프를 오탐으로 막게 된다.

    initial_state()가 항상 채워주는 키(_PRESEEDED_STATE_KEYS)는 io.input 노드가
    캔버스에 없어도 항상 충족된 것으로 본다.
    """
    write_keys: set[str] = set()
    for node in nodes:
        manifest = MANIFESTS_BY_TYPE.get(node["type"])
        if manifest and manifest.get("runtime") == "llm_step":
            spec = LLM_STEP_TABLE.get(node["type"], {})
            write_keys.update(spec.get("writes", []))

    for node in nodes:
        manifest = MANIFESTS_BY_TYPE.get(node["type"])
        if not manifest or manifest.get("runtime") != "llm_step":
            continue
        for port in manifest["inputs"]:
            if not port.get("required"):
                continue
            key = port["id"]
            if key in _PRESEEDED_STATE_KEYS or key in write_keys:
                continue
            raise ValueError(
                f"node {node['id']!r} requires input {key!r} but no node in this "
                "architecture writes it, and it is not provided by the run's initial input"
            )
```

- [ ] **Step 5: Wire it into `compile_graph`**

In `server/graphs/compile.py`, in `compile_graph` (around line 487-490), replace:
```python
    if not nodes:
        raise ValueError("Architecture has no nodes")

    edges = _filter_control_edges(nodes, raw_edges)
```
with:
```python
    if not nodes:
        raise ValueError("Architecture has no nodes")
    _validate_required_inputs(nodes)

    edges = _filter_control_edges(nodes, raw_edges)
```

- [ ] **Step 6: Run the full test file to verify everything passes**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -v`
Expected: all tests PASS.

- [ ] **Step 7: Lint and commit**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .`

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "$(cat <<'EOF'
feat(compile): add Tier 1 required-input existence validator

Freeform ports remove the canvas's implicit validation (a required
port used to be visibly empty). This adds the safe, no-false-positive
half of that back: an llm_step-runtime node's required input must be
either seeded by initial_state() or written by some node in the graph,
checked at compile time before any model call. Scoped to llm_step
runtimes only — review/checkpoint/loop_guard read fixed keys from
their own code rather than manifest-declared ports, so validating
their required flags would flag decorative ports (e.g. io.output's
"result", which no runtime code ever reads) as missing.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

---

### Task 4: `_build_plain_edge_plan` — the AND/OR join decision (pure function)

**Files:**
- Modify: `server/graphs/compile.py` (new code, placed before `compile_graph`)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Produces: `_CONDITIONAL_ROUTING_TYPES: set[str]` and `_build_plain_edge_plan(nodes: list[dict], edges: list[dict]) -> list[tuple[list[str], str]]`. Task 5 consumes this directly to drive the actual `graph.add_edge(...)` calls.
- This task adds no wiring into `compile_graph` yet — it is a pure function, fully testable in isolation. Task 5 does the wiring.

- [ ] **Step 1: Write the failing unit tests**

Add to `server/tests/test_compile.py`:

```python
def test_build_plain_edge_plan_single_source_is_not_joined():
    nodes = [_node("a", "reasoning.cot"), _node("b", "io.output")]
    edges = [_edge("a", "b", "answer")]
    assert compile_mod._build_plain_edge_plan(nodes, edges) == [(["a"], "b")]


def test_build_plain_edge_plan_requires_join_mode_for_two_plain_sources():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        _node("c", "io.output"),  # joinMode 미선언
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)


def test_build_plain_edge_plan_creates_a_single_join_edge_for_and():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "and"},
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["a", "b"], "c")]


def test_build_plain_edge_plan_keeps_individual_edges_for_or():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "or"},
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert sorted(plan) == [(["a"], "c"), (["b"], "c")]


def test_build_plain_edge_plan_forces_or_when_a_conditional_source_is_mixed_in():
    """review.intent/loop.guard/human.checkpoint 같은 conditional-routing 소스가
    하나라도 섞이면 AND가 구조적으로 불가능하다 — 이 셋은 add_conditional_edges나
    Command(goto=...)로 스스로 라우팅하고 add_edge를 절대 호출하지 않으므로
    LangGraph의 join-edge에 참여할 수 없다. joinMode 선언 자체를 요구하지 않고
    나머지 plain 소스도 자동으로 개별 엣지가 된다 (설계 §4)."""
    nodes = [
        _node("input", "io.input"),
        _node("guard", "loop.guard"),
        _node("reasoning", "reasoning.cot"),  # joinMode 미선언이어도 에러 없어야 함
    ]
    edges = [
        _edge("input", "reasoning", "task"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["input"], "reasoning")]  # guard발 엣지는 plan에 아예 안 들어감


def test_build_plain_edge_plan_excludes_review_sourced_edges_entirely():
    nodes = [_node("review", "review.intent"), _node("output", "io.output")]
    edges = [_edge("review", "output", "accept")]
    assert compile_mod._build_plain_edge_plan(nodes, edges) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "build_plain_edge_plan" -v`
Expected: FAIL — `_build_plain_edge_plan` doesn't exist yet.

- [ ] **Step 3: Implement `_CONDITIONAL_ROUTING_TYPES` and `_build_plain_edge_plan`**

In `server/graphs/compile.py`, add this immediately before `def compile_graph(` (before line 483):

```python
_CONDITIONAL_ROUTING_TYPES = {"review.intent", "human.checkpoint", "loop.guard"}


def _build_plain_edge_plan(nodes: list[dict], edges: list[dict]) -> list[tuple[list[str], str]]:
    """일반(비-분기) 엣지들을 (sources, target) 쌍의 리스트로 계획한다. 소스가
    2개 이상이면 리스트에 그대로 담기고, 호출부가 graph.add_edge(sources, target)로
    넘기면 LangGraph의 join-edge(모든 소스가 끝날 때까지 대기)가 된다. 소스가
    1개면 [source] 하나짜리 리스트 — 호출부는 graph.add_edge(source, target)로
    개별 등록한다 (설계 §4).

    review.intent/human.checkpoint/loop.guard가 소스인 엣지는 여기서 완전히
    제외된다 — 이 셋은 add_conditional_edges/Command(goto=...)로 스스로 라우팅하고
    절대 일반 add_edge를 호출하지 않으므로, 이 노드들이 소스인 엣지는 애초에
    LangGraph의 join-edge에 참여할 수 없다. 어떤 target이 이런 소스를 하나라도
    가지면 joinMode 선언 자체를 요구하지 않고(항상 OR 취급), 그 target으로 가는
    나머지 plain 소스들도 개별 add_edge로 처리한다.
    """
    nodes_by_id = {n["id"]: n for n in nodes}
    plain_sources_by_target: dict[str, list[str]] = {}
    has_conditional_source: dict[str, bool] = {}

    for e in edges:
        target = e["target"]
        source_type = nodes_by_id.get(e["source"], {}).get("type")
        if source_type in _CONDITIONAL_ROUTING_TYPES:
            has_conditional_source[target] = True
            continue
        sources = plain_sources_by_target.setdefault(target, [])
        if e["source"] not in sources:
            sources.append(e["source"])

    plan: list[tuple[list[str], str]] = []
    for target, sources in plain_sources_by_target.items():
        if len(sources) >= 2 and not has_conditional_source.get(target, False):
            join_mode = nodes_by_id[target].get("joinMode")
            if join_mode not in ("and", "or"):
                raise ValueError(
                    f"node {target!r} has {len(sources)} incoming plain edges and no "
                    "joinMode — choose 'and' or 'or' in Inspector"
                )
            if join_mode == "and":
                plan.append((sources, target))
                continue
        for source in sources:
            plan.append(([source], target))
    return plan
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -v`
Expected: all tests PASS. `_build_plain_edge_plan` is not called from `compile_graph` yet, so this is purely additive — no existing test should change behavior.

- [ ] **Step 5: Lint and commit**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .`

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "$(cat <<'EOF'
feat(compile): add _build_plain_edge_plan for AND/OR join decisions

Pure function, not yet wired into compile_graph. Groups plain edges by
target and decides, per target with 2+ plain-runtime sources, whether
to emit a single LangGraph join-edge (add_edge([sources], target),
AND) or individual add_edge calls (OR / ambiguous). Targets with any
conditional-routing source (review.intent/human.checkpoint/loop.guard)
are forced to OR without requiring a joinMode declaration, since those
three runtimes never call add_edge and so cannot participate in a
join-edge regardless of what the user picks.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

---

### Task 5: Wire the AND/OR join plan into `compile_graph`

**Files:**
- Modify: `server/graphs/compile.py:585-609` (the plain-edge-wiring loop)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Consumes: `_build_plain_edge_plan` (Task 4).
- No new public functions — this task replaces `compile_graph`'s internal edge-wiring loop to call `graph.add_edge` per the plan instead of unconditionally per-edge.

- [ ] **Step 1: Write the failing integration tests**

Add to `server/tests/test_compile.py`. The first test is the real TDD red/green check — it fails before Step 3 because `compile_graph` doesn't call `_build_plain_edge_plan` yet, so a missing `joinMode` is silently ignored rather than rejected. The other two are integration confirmations for the two branches of the now-wired behavior (they already succeed before Step 3 too, since the old unconditional per-edge loop doesn't look at `joinMode` at all — their job is to prove the *new* code path produces a correctly-running graph, not to be red beforehand):

```python
async def test_compile_graph_requires_join_mode_for_two_plain_sources(monkeypatch):
    """_build_plain_edge_plan이 compile_graph에 실제로 연결돼 있는지 확인 — 2개 이상의
    plain 소스가 한 target으로 모이는데 joinMode가 없으면 컴파일 에러여야 한다."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),  # joinMode 미선언
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_compile_graph_and_join_compiles_and_runs(monkeypatch):
    """joinMode='and'를 선언하면 컴파일 에러 없이 join-edge로 컴파일되고, 두 plain
    소스(planning/reasoning) 각각의 결과가 전부 최종 state에 반영된 채로 완주한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            {**_node("output", "io.output"), "joinMode": "and"},
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state("2+2"), {"configurable": {"thread_id": "t-and"}})
    assert final.get("plan") == ["s1"]
    assert final.get("answer") == "4"


async def test_compile_graph_or_join_still_compiles_and_runs(monkeypatch):
    """joinMode='or'도 여전히 컴파일·실행된다 — 개별 add_edge 그대로 (회귀)."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            {**_node("output", "io.output"), "joinMode": "or"},
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state("2+2"), {"configurable": {"thread_id": "t-or"}})
    assert final.get("plan") == ["s1"]
    assert final.get("answer") == "4"
```

- [ ] **Step 2: Run the tests to verify the first one fails**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "requires_join_mode_for_two_plain_sources" -v`
Expected: FAIL — `Failed: DID NOT RAISE <class 'ValueError'>`. The other two new tests (`and_join_compiles_and_runs`, `or_join_still_compiles_and_runs`) are expected to already PASS at this point — confirm with `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -k "and_join_compiles_and_runs or or_join_still_compiles_and_runs" -v` and treat anything other than PASS there as a sign the test fixtures themselves are wrong, not that Step 3 is needed to make them pass.

- [ ] **Step 3: Replace the plain-edge-wiring loop in `compile_graph`**

In `server/graphs/compile.py`, replace the block (lines 585-609):

```python
    added_plain_edges: set[tuple[str, str]] = set()
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        outs = outgoing.get(node_id, [])

        if node_type == "review.intent":
            graph.add_conditional_edges(
                node_id, route_fns[node_id], _handle_targets(outgoing, node_id)
            )
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
```

with:

```python
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]

        if node_type == "review.intent":
            graph.add_conditional_edges(
                node_id, route_fns[node_id], _handle_targets(outgoing, node_id)
            )
            continue
        # human.checkpoint / loop.guard는 Command(goto=...)로 스스로 라우팅하므로
        # plain edge를 추가하지 않는다.
        if node_type in ("human.checkpoint", "loop.guard"):
            continue
        if not outgoing.get(node_id):
            graph.add_edge(node_id, END)

    for sources, target in _build_plain_edge_plan(nodes, edges):
        if len(sources) > 1:
            graph.add_edge(sources, target)
        else:
            graph.add_edge(sources[0], target)
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest tests/test_compile.py -v`
Expected: all tests PASS — including every pre-existing test (this is the step that proves the "migration is free" claim: `_gated_refine_arch`-shaped graphs, used by several existing tests, have exactly one plain source into `reasoning` — `input` — mixed with `guard`'s conditional `loopBack` edge, so they never hit the "needs joinMode" branch and keep compiling with no `joinMode` field at all).

- [ ] **Step 5: Lint and commit**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format .`

```bash
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "$(cat <<'EOF'
feat(compile): wire AND/OR join plan into compile_graph's edge wiring

Replaces the unconditional per-edge add_edge loop with
_build_plain_edge_plan's decision: a target with 2+ plain-runtime
incoming edges and joinMode='and' gets a single add_edge([sources],
target) LangGraph join-edge (verified to wait for all sources
regardless of superstep timing); everything else keeps today's
individual add_edge behavior. Confirmed the starter-architecture-shaped
graphs (mixed plain + conditional-routing sources) compile with no
joinMode declared at all, matching the "migration is free" claim.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

---

### Task 6: Full-suite regression and final verification

**Files:**
- None modified — verification only.

**Interfaces:**
- None — this task confirms Tasks 1-5 didn't regress anything outside `test_compile.py`.

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/pytest -v`
Expected: all tests PASS across every file in `server/tests/`, not just `test_compile.py` (e.g. `test_policy.py`, `test_graph_treatment.py`, `test_workspace.py` per `CLAUDE.local.md`'s inventory — this confirms `_handle_targets`'s role-resolution change and the `LLM_STEP_TABLE` schema change didn't break anything outside `compile.py`'s own tests).

- [ ] **Step 2: Run ruff over the whole backend**

Run: `cd /home/licodev/projects/agentforge/server && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: no errors. If `ruff format --check` reports unformatted files, run `.venv/bin/ruff format .` and re-check.

- [ ] **Step 3: If Steps 1-2 required any fixes, commit them**

```bash
cd /home/licodev/projects/agentforge
git status
```

If there are unstaged changes from lint fixes, stage and commit them:

```bash
git add server/
git commit -m "$(cat <<'EOF'
chore(compile): final lint pass for Phase A1 backend

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VeWVDnBvNy5qR8CxJVnP3E
EOF
)"
```

If nothing changed, this task is complete with no commit needed.

---

## What this plan does NOT cover (explicitly out of scope)

- Any file under `ui/` — the frontend Zod schema (`sourceRole`/`joinMode` fields), canvas connection UX, Inspector role/join-mode UI, and the three Loop Scope files (`deriveLoopMembers.ts`, `loopProjection.ts`, `hubRimAngles.ts`) from spec §7. That's a separate follow-up plan.
- Phase A2 (dispatch normalization to `runtime`) and any changes to `_filter_control_edges` — spec explicitly defers both.
- Phase B (node type templates, `AgentState.vars`, output-schema data-driven `LLM_STEP_TABLE`) — separate phase, separate plan, comes after both A1 and A2.
