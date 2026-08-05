"""graphs/compile.py 단위 테스트 — Architecture → StateGraph 컴파일. LLM은 목(AGENTS.md §6)."""

import pytest

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
