"""treatment 그래프 통합 테스트 — review의 refine 루프와 accept 경로. LLM은 목(AGENTS.md §6)."""

import graphs.treatment as treatment
import nodes.review as review_mod
from events import ListEventEmitter
from state import initial_state


def _delta(per_criterion=None, misalignments=None):
    return {
        "per_criterion": per_criterion or [],
        "misalignments": misalignments or [],
        "elicit_questions": [],
        "proposed_criteria": [],
        "reroute_hint": "",
    }


async def test_treatment_refines_then_accepts(monkeypatch):
    review_calls = {"n": 0}

    async def fake_run_llm_step(state, *, node_id, **kwargs):
        if node_id == "planning":
            return {"steps": ["step 1"]}
        if node_id == "reasoning":
            return {"answer": "42", "confidence": 0.5}
        # review: 1회차 must_pass unmet → refine, 2회차 전부 met → accept
        review_calls["n"] += 1
        if review_calls["n"] == 1:
            return _delta([{"id": "g1", "verdict": "unmet", "evidence": "단위 없음"}])
        return _delta()

    monkeypatch.setattr(treatment, "run_llm_step", fake_run_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", fake_run_llm_step)

    emitter = ListEventEmitter()
    graph = treatment.build_treatment(model=None, emit=emitter, run_id="run-t")

    state0 = initial_state(task="2+2", batch_mode=True)
    final = await graph.ainvoke(state0, config={"configurable": {"thread_id": "run-t"}})

    assert review_calls["n"] == 2
    assert final["review_branch"] == "accept"
    assert final["retries"] == 1
    assert "unmet" in (final.get("feedback") or "")  # refine 시 unmet delta가 피드백으로 전달됨

    decisions = [e.policy_decision for e in emitter.events if e.policy_decision]
    assert [d["branch"] for d in decisions] == ["refine", "accept"]

    by_node = {(e.node_id, e.event_type) for e in emitter.events}
    assert ("review", "node_start") in by_node
    assert ("review", "node_end") in by_node
    assert ("output", "node_end") in by_node


async def test_treatment_batch_demotes_clarify(monkeypatch):
    async def fake_run_llm_step(state, *, node_id, **kwargs):
        if node_id == "planning":
            return {"steps": ["step 1"]}
        if node_id == "reasoning":
            return {"answer": "42", "confidence": 0.5}
        return _delta(misalignments=["의도와 다른 형식"])  # clarify 감

    monkeypatch.setattr(treatment, "run_llm_step", fake_run_llm_step)
    monkeypatch.setattr(review_mod, "run_llm_step", fake_run_llm_step)

    emitter = ListEventEmitter()
    graph = treatment.build_treatment(model=None, emit=emitter, run_id="run-b")

    state0 = initial_state(task="2+2", batch_mode=True)
    final = await graph.ainvoke(state0, config={"configurable": {"thread_id": "run-b"}})

    # batch_mode: clarify → accept 강등, interrupt 없이 완주 + demoted 표시
    assert final["review_branch"] == "accept"
    decision = next(e.policy_decision for e in emitter.events if e.policy_decision)
    assert decision["demoted"] is True
    assert "batch demoted" in decision["reason"]
