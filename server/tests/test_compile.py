"""graphs/compile.py 단위 테스트 — Architecture → StateGraph 컴파일. LLM은 목(AGENTS.md §6)."""

import pytest
from langgraph.types import Command

import graphs.compile as compile_mod
import nodes.review as review_mod
from events import ListEventEmitter
from state import initial_state

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
    """모든 노드에 incoming이 있으면(순환) 진입점 부재 ValueError."""
    _patch_model(monkeypatch)
    arch = _arch(
        [_node("a", "reasoning.cot"), _node("b", "reasoning.cot")],
        [_edge("a", "b"), _edge("b", "a")],
    )
    with pytest.raises(ValueError, match="no entry"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, None, "run-1")


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
    """review의 refine 핸들→reasoning 루프 후 accept 핸들→output."""
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
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "reasoning", "refine"),
            _edge("review", "output", "accept"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    criteria = [{"id": "c1", "text": "정답 포함", "severity": "must_pass"}]
    final = await graph.ainvoke(
        initial_state("", criteria=criteria, intent="정확한 계산"),
        {"configurable": {"thread_id": "t3"}},
    )

    assert final["review_branch"] == "accept"
    assert final["retries"] == 1
    branches = [e.policy_decision["branch"] for e in emitter.events if e.policy_decision]
    assert branches == ["refine", "accept"]


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


async def test_loop_policy_invalid_on_exhaustion_raises(monkeypatch):
    _patch_model(monkeypatch)
    refine_edge = _edge("review", "reasoning", "refine")
    exit_edge = _edge("review", "output", "clarify")
    arch = _arch(
        [
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [_edge("reasoning", "review", "answer"), refine_edge, exit_edge],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[refine_edge["id"]],
            memberNodeIds=["reasoning", "review"],
            exitEdgeIds=[exit_edge["id"]],
            onExhaustion="not_a_real_value",
        )
    ]
    with pytest.raises(ValueError, match="invalid onExhaustion"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_policy_missing_id_raises(monkeypatch):
    _patch_model(monkeypatch)
    refine_edge = _edge("review", "reasoning", "refine")
    exit_edge = _edge("review", "output", "clarify")
    arch = _arch(
        [
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [_edge("reasoning", "review", "answer"), refine_edge, exit_edge],
    )
    policy = _loop_policy(
        feedbackEdgeIds=[refine_edge["id"]],
        memberNodeIds=["reasoning", "review"],
        exitEdgeIds=[exit_edge["id"]],
    )
    del policy["id"]
    arch["loopPolicies"] = [policy]
    with pytest.raises(ValueError, match="missing required field 'id'"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


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


async def test_loop_policy_on_human_checkpoint_feedback_edge_reaches_guard_via_dynamic_goto(
    monkeypatch,
):
    """human.checkpoint의 revise 피드백 엣지에 붙은 LoopPolicy가 실제로 동작한다.

    review.intent 경로는 guard가 add_conditional_edges의 선언된 branch mapping을 통해
    도달되지만, human.checkpoint는 edge-wiring 루프에서 완전히 스킵되고
    make_human_checkpoint()이 Command(goto=routes[action])으로만 분기한다 — 즉 guard
    노드는 정적 edge도, 선언된 branch mapping도 전혀 없이 오직 동적 goto만으로
    도달된다. LangGraph가 (지금은 하지 않는) goto 타깃 reachability 검증을 추가하는
    업그레이드가 오면 이 경로만 조용히 깨질 수 있어, 실제 interrupt/resume 사이클로
    도달·동작을 증명해 둔다.
    """
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    revise_edge = _edge("checkpoint", "reasoning", "revise")
    approve_edge = _edge("checkpoint", "output", "approve")
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("checkpoint", "human.checkpoint"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "checkpoint", "answer"),
            revise_edge,
            approve_edge,
        ],
    )
    arch["loopPolicies"] = [
        _loop_policy(
            feedbackEdgeIds=[revise_edge["id"]],
            memberNodeIds=["reasoning", "checkpoint"],
            exitEdgeIds=[approve_edge["id"]],
            guard={"maxIterations": 1},
        )
    ]
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    config = {"configurable": {"thread_id": "t-loop-checkpoint"}}

    first = await graph.ainvoke(initial_state(""), config)
    assert first.get("__interrupt__")  # checkpoint에서 일시정지

    # 1차 revise: guard의 첫 iteration(1)은 maxIterations=1 미달 → continue → reasoning
    # 재실행 → checkpoint가 다시 일시정지한다. dynamic goto만으로 guard에 도달했다는 증거.
    second = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert second.get("__interrupt__")

    # 2차 revise: guard의 iteration(2)이 maxIterations=1을 트립 → exitEdgeIds(output)로
    # 강제 이탈 → 그래프가 완주한다(더 이상 interrupt 없음).
    final = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert not final.get("__interrupt__")
    assert final["answer"] == "4"

    guard_events = [
        e for e in emitter.events if e.node_id == "__loop_guard__loop-1" and e.loop_runtime
    ]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2]
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"


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
