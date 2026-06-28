"""baseline 그래프 회귀 테스트.

과거 버그: reasoning/output 노드가 도메인 필드(answer/confidence/verdict)를
make_event에 top-level kwarg로 넘겨 ExecutionEvent.__init__에서 TypeError가 났다.
이제는 output={...}으로 감싸야 한다. LLM 호출(run_llm_step)은 목으로 대체한다 (AGENTS.md §6).
"""
import graphs.baseline as baseline
from events import ListEventEmitter
from state import initial_state


async def test_baseline_emits_valid_node_end_events(monkeypatch):
    async def fake_run_llm_step(state, **kwargs):
        return {"answer": "42", "confidence": 0.9}

    monkeypatch.setattr(baseline, "run_llm_step", fake_run_llm_step)

    emitter = ListEventEmitter()
    graph = baseline.build_baseline(model=None, emit=emitter, run_id="run-1")

    state0 = initial_state(task="2+2", task_tags=[])
    config = {"configurable": {"thread_id": "run-1"}}
    # 버그가 있으면 여기서 TypeError가 난다.
    await graph.ainvoke(state0, config=config)

    by_node = {(e.node_id, e.event_type) for e in emitter.events}
    assert ("reasoning", "node_start") in by_node
    assert ("reasoning", "node_end") in by_node
    assert ("output", "node_end") in by_node

    reasoning_end = next(
        e for e in emitter.events
        if e.node_id == "reasoning" and e.event_type == "node_end"
    )
    assert reasoning_end.output == {"answer": "42", "confidence": 0.9}
