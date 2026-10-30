"""Regression test for the baseline graph.

Past bug: the reasoning/output nodes passed domain fields (answer/confidence/verdict) to
make_event as top-level kwargs, causing a TypeError in ExecutionEvent.__init__.
They must now be wrapped as output={...}. The LLM call (run_llm_step) is mocked (AGENTS.md §6).
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
    # If the bug is present, a TypeError is raised here.
    await graph.ainvoke(state0, config=config)

    by_node = {(e.node_id, e.event_type) for e in emitter.events}
    assert ("reasoning", "node_start") in by_node
    assert ("reasoning", "node_end") in by_node
    assert ("output", "node_end") in by_node

    reasoning_end = next(
        e for e in emitter.events if e.node_id == "reasoning" and e.event_type == "node_end"
    )
    assert reasoning_end.output == {"answer": "42", "confidence": 0.9}
