"""graphs/compile.py 단위 테스트 — Architecture → StateGraph 컴파일. LLM은 목(AGENTS.md §6)."""

import pytest
from langgraph.types import Command

import graphs.compile as compile_mod
import nodes.review as review_mod
from events import ListEventEmitter
from nodes.loop_guard import evaluate_loop_guard
from state import empty_loop_runtime, initial_state

DEFAULT_MODEL_CFG = {"provider": "anthropic", "model": "claude-3", "temperature": 0}


def _arch(nodes, edges):
    return {"version": "1", "metadata": {"name": "test"}, "nodes": nodes, "edges": edges}


def _node(id_, type_, config=None):
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "config": config or {}}


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


def _delta(per_criterion=None, misalignments=None):
    return {
        "per_criterion": per_criterion or [],
        "misalignments": misalignments or [],
        "elicit_questions": [],
        "proposed_criteria": [],
        "reroute_hint": "",
    }


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


async def fake_llm_step(state, *, node_id, **kwargs):
    if node_id == "planning":
        return {"steps": ["s1"]}
    if node_id == "reasoning":
        return {"answer": "4", "confidence": 0.9}
    return {}


def _patch_model(monkeypatch):
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)


async def test_compile_no_nodes_raises():
    """노드가 없는 아키텍처는 ValueError."""
    with pytest.raises(ValueError, match="no nodes"):
        compile_mod.compile_graph(_arch([], []), DEFAULT_MODEL_CFG, None, "run-1")


async def test_compile_unknown_type_raises():
    """미등록 노드 타입은 ValueError."""
    arch = _arch([_node("unknown", "foo.bar")], [])
    with pytest.raises(ValueError, match="Unknown node type"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, None, "run-1")


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


def test_filter_control_edges_unit():
    """io.input발 엣지는 target에 실제 처리 선행 노드가 있을 때만 제거된다."""
    nodes = [
        _node("input", "io.input"),
        _node("planning", "planning.decompose"),
        _node("reasoning", "reasoning.cot"),
    ]
    edges = [
        _edge("input", "reasoning"),
        _edge("input", "planning"),
        _edge("planning", "reasoning"),
    ]
    filtered = compile_mod._filter_control_edges(nodes, edges)
    pairs = {(e["source"], e["target"]) for e in filtered}
    assert pairs == {("input", "planning"), ("planning", "reasoning")}


async def test_linear_pipeline_runs(monkeypatch):
    """input→planning→reasoning→output 선형 파이프라인 컴파일·실행."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "planning", "task"),
            _edge("planning", "reasoning", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t1"}})

    assert final["task"] == "2+2"  # io.input sample이 task를 시드
    assert final["plan"] == ["s1"]
    assert final["answer"] == "4"
    starts = {e.node_id for e in emitter.events if e.event_type == "node_start"}
    ends = {e.node_id for e in emitter.events if e.event_type == "node_end"}
    assert starts == ends == {"input", "planning", "reasoning", "output"}


async def test_input_prefers_submitted_task_over_canvas_sample(monkeypatch):
    """WebSocket 등 실행 시 제출한 task는 io.input sample보다 우선한다."""
    _patch_model(monkeypatch)
    observed_tasks: list[str] = []

    async def capture_task(state, *, node_id, **kwargs):
        observed_tasks.append(state["task"])
        return await fake_llm_step(state, node_id=node_id, **kwargs)

    monkeypatch.setattr(compile_mod, "run_llm_step", capture_task)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "canvas sample"}),
            _node("reasoning", "reasoning.cot"),
        ],
        [_edge("input", "reasoning", "task")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(
        initial_state("submitted task"), {"configurable": {"thread_id": "t3"}}
    )

    assert final["task"] == "submitted task"
    assert observed_tasks == ["submitted task"]
    input_end = next(
        e for e in emitter.events if e.node_id == "input" and e.event_type == "node_end"
    )
    assert input_end.output == {"task": "submitted task"}


async def test_reasoning_direct_no_planning(monkeypatch):
    """planning 없이 input→reasoning→output도 동작한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),
        ],
        [_edge("input", "reasoning", "task"), _edge("reasoning", "output", "answer")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t2"}})
    assert final["answer"] == "4"


async def test_node_positions_do_not_change_compiled_execution(monkeypatch):
    """캔버스 좌표는 표현 전용이며 컴파일된 실행 순서에 영향을 주지 않는다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    base_nodes = [
        _node("input", "io.input", {"sample": "2+2"}),
        _node("reasoning", "reasoning.cot"),
        _node("output", "io.output"),
    ]
    edges = [_edge("input", "reasoning", "task"), _edge("reasoning", "output", "answer")]
    radial_nodes = [
        {**node, "position": {"x": index * 320 - 160, "y": index * index * 90}}
        for index, node in enumerate(base_nodes)
    ]
    emitters = [ListEventEmitter(), ListEventEmitter()]

    finals = []
    for arch_nodes, emitter, thread_id in zip(
        (base_nodes, radial_nodes), emitters, ("vertical", "radial"), strict=True
    ):
        graph = compile_mod.compile_graph(
            _arch(arch_nodes, edges), DEFAULT_MODEL_CFG, emitter, "run-positions"
        )
        finals.append(
            await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": thread_id}})
        )

    assert [final["answer"] for final in finals] == ["4", "4"]
    event_nodes = [
        [event.node_id for event in emitter.events if event.event_type == "node_start"]
        for emitter in emitters
    ]
    assert event_nodes == [["input", "reasoning", "output"]] * 2


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


async def test_review_unwired_branch_falls_back(monkeypatch):
    """미배선 브랜치는 wired 기반 폴백으로 라우팅돼 그래프가 END에 도달한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    async def always_unmet(state, *, node_id, **kwargs):
        return _delta([{"id": "c1", "verdict": "unmet", "evidence": "부족"}])

    monkeypatch.setattr(review_mod, "run_llm_step", always_unmet)
    emitter = ListEventEmitter()
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
            _edge("review", "output", "accept"),  # refine/clarify 미배선
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, batch_mode=True),
        {"configurable": {"thread_id": "t4"}},
    )

    assert final.get("answer") == "4"
    assert any(e.node_id == "output" and e.event_type == "node_end" for e in emitter.events)


async def test_human_checkpoint_compiles(monkeypatch):
    """human.checkpoint 포함 아키텍처가 예외 없이 컴파일된다 (invoke 안 함)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("checkpoint", "human.checkpoint"),
            _node("output", "io.output"),
        ],
        [_edge("input", "checkpoint", "task"), _edge("checkpoint", "output", "approve")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
    assert graph is not None


async def test_model_binding_ignored_in_flow(monkeypatch):
    """엣지 없는 model.binding은 흐름에 영향 없이 통과한다."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("binding", "model.binding"),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),
        ],
        [_edge("input", "reasoning", "task"), _edge("reasoning", "output", "answer")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t5"}})
    assert final["answer"] == "4"


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
    guard = compile_mod._loop_policy_from_config(_node("guard", "loop.guard", {"stuckWindow": 3}))[
        "guard"
    ]

    assert guard == {"stuck": {"window": 3}}
    assert evaluate_loop_guard(
        {"guard": guard},
        {**empty_loop_runtime(), "iteration": 3, "progress_history": [4.0, 4.0, 4.0]},
    ) == {"should_continue": False, "exit_reason": "stuck"}


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
        compile_mod._validate_gated_cycles(["a", "b"], [_edge("a", "b"), _edge("b", "a")], set())


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


def test_validate_gated_cycles_rejects_an_ungated_cycle_sharing_a_node_with_a_gated_one():
    """Tarjan은 노드를 공유하는 cycle을 하나의 컴포넌트로 합친다 — guard가 있는 cycle과
    없는 cycle이 노드 하나만 공유해도 가드 없이 그린 cycle이 조용히 통과해서는 안 된다."""
    edges = [
        _edge("reasoning", "review"),
        _edge("review", "guard"),
        _edge("guard", "reasoning"),
        _edge("reasoning", "critic"),
        _edge("critic", "reasoning"),
    ]
    with pytest.raises(ValueError, match=r"\['critic', 'reasoning'\]"):
        compile_mod._validate_gated_cycles(
            ["reasoning", "review", "guard", "critic"], edges, {"guard"}
        )


def test_validate_gated_cycles_still_accepts_a_purely_gated_cycle():
    edges = [_edge("a", "g"), _edge("g", "a")]
    compile_mod._validate_gated_cycles(["a", "g"], edges, {"g"})


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


async def test_loop_guard_loopback_port_fanout_raises(monkeypatch):
    """loopBack 포트에 outgoing edge가 2개 이상이면 _handle_targets가 마지막 것만
    남기고 나머지를 조용히 버리므로, 컴파일 에러로 막아야 한다."""
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
            _edge("guard", "review", "loopBack", "in"),
            _edge("guard", "output", "exit", "result"),
        ],
    )
    with pytest.raises(ValueError, match=r"2 edges assigned the 'loopBack' role"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_exit_port_fanout_raises(monkeypatch):
    """exit 포트도 loopBack과 마찬가지로 outgoing edge가 2개 이상이면 컴파일 에러다."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("output", "io.output"),
            _node("output2", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
            _edge("guard", "output2", "exit", "result"),
        ],
    )
    with pytest.raises(ValueError, match=r"2 edges assigned the 'exit' role"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


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


def test_build_plain_edge_plan_raises_cleanly_for_a_dangling_edge_target():
    """target이 nodes 목록에 없는 경우(프리폼 캔버스에서 노드가 삭제됐지만 그 노드를
    가리키던 엣지가 남아있는 경우) source 조회와 동일하게 방어적으로 처리해야 한다 —
    KeyError로 죽지 않고 기존 '설정 오류'(joinMode 없음) ValueError로 자연스럽게
    흡수돼야 한다."""
    nodes = [_node("a", "planning.decompose"), _node("b", "reasoning.cot")]
    edges = [_edge("a", "missing", "plan"), _edge("b", "missing", "answer")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)


def test_build_plain_edge_plan_forces_or_with_two_plain_sources_and_a_conditional_source():
    """conditional-routing 소스가 하나라도 섞이면, plain 소스가 2개 이상이어도 AND는
    구조적으로 불가능하다 — joinMode 선언 없이도 에러 없이 개별 엣지로 처리돼야 한다
    (설계 §4의 핵심 시나리오: starter architecture에서 guard가 다른 plain 소스들과
    함께 하나의 target으로 들어오는 경우)."""
    nodes = [
        _node("planning", "planning.decompose"),
        _node("reasoning", "reasoning.cot"),
        _node("guard", "loop.guard"),
        _node("target", "io.output"),  # joinMode 미선언이어도 에러 없어야 함
    ]
    edges = [
        _edge("planning", "target", "plan"),
        _edge("reasoning", "target", "answer"),
        _edge("guard", "target", "loopBack", "task"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert sorted(plan) == [(["planning"], "target"), (["reasoning"], "target")]


def test_build_plain_edge_plan_dedups_multiple_edges_from_the_same_source_target_pair():
    """같은 (source, target) 쌍에서 나온 엣지가 여러 개(예: 서로 다른 데이터 포트로
    두 번 연결)여도 소스는 한 번만 카운트돼야 한다 — join된 소스 리스트에 중복 없이
    한 번만 나타나야 한다."""
    nodes = [
        _node("a", "planning.decompose"),
        _node("d", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "and"},
    ]
    edges = [
        _edge("a", "c", "plan1", "in1"),
        _edge("a", "c", "plan2", "in2"),
        _edge("d", "c", "answer"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["a", "d"], "c")]


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
