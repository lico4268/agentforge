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


def _edge(source, target, source_handle="out", target_handle="in"):
    return {
        "id": f"e-{source}-{target}",
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }


def _delta(per_criterion=None, misalignments=None):
    return {
        "per_criterion": per_criterion or [],
        "misalignments": misalignments or [],
        "elicit_questions": [],
        "proposed_criteria": [],
        "reroute_hint": "",
    }


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
