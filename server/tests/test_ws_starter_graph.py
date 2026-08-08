"""ws_run → dispatch_graph → compile_graph 전체 경로를, loop.guard가 들어간 스타터
그래프 그대로 통과시키는 통합 테스트. LLM은 목(AGENTS.md §6).

단위 테스트만 통과하고 실제로는 한 번도 실행되지 않은 채 머지된 8/6 사고를 막는
장치다 — 여기가 깨지면 브라우저에서 Run 버튼을 눌렀을 때 깨진다는 뜻이다.
토폴로지(노드 id, 엣지 id, 엣지 배선, loop.guard config)는 ui/src/app/starterArchitecture.ts와
1:1로 유지한다 — 단, io.input.config.sample은 여기선 짧은 "2+2"로 의도적으로 다르고
(TS 쪽은 실제 Natalia 문장제), modelSlots는 LLM을 목으로 대체하므로 생략돼 있다.
"""

from fastapi.testclient import TestClient

import graphs.compile as compile_mod
import nodes.review as review_mod
import workspace as workspace_mod

STARTER_ARCHITECTURE = {
    "version": "0.1",
    "metadata": {"name": "GSM8K Treatment (starter)", "createdAt": "2026-08-07T00:00:00.000Z"},
    "nodes": [
        {
            "id": "input",
            "type": "io.input",
            "position": {"x": 96, "y": 88},
            "config": {"sample": "2+2"},
        },
        {
            "id": "planning",
            "type": "planning.decompose",
            "position": {"x": 272, "y": 220},
            "config": {},
        },
        {
            "id": "reasoning",
            "type": "reasoning.cot",
            "position": {"x": 472, "y": 356},
            "config": {},
        },
        {
            "id": "review",
            "type": "review.intent",
            "position": {"x": 690, "y": 300},
            "config": {"criteria": [], "maxRetries": 2},
        },
        {
            "id": "loop_guard",
            "type": "loop.guard",
            "position": {"x": 916, "y": 430},
            "config": {"kind": "critiqueRevise", "maxIterations": 3, "onExhaustion": "exit"},
        },
        {
            "id": "human_checkpoint",
            "type": "human.checkpoint",
            "position": {"x": 748, "y": 520},
            "config": {},
        },
        {"id": "output", "type": "io.output", "position": {"x": 522, "y": 616}, "config": {}},
    ],
    "edges": [
        {
            "id": "e1",
            "source": "input",
            "sourceHandle": "task",
            "target": "planning",
            "targetHandle": "task",
        },
        {
            "id": "e2",
            "source": "planning",
            "sourceHandle": "plan",
            "target": "reasoning",
            "targetHandle": "plan",
        },
        {
            "id": "e3",
            "source": "input",
            "sourceHandle": "task",
            "target": "reasoning",
            "targetHandle": "task",
        },
        {
            "id": "e4",
            "source": "reasoning",
            "sourceHandle": "answer",
            "target": "review",
            "targetHandle": "answer",
        },
        {
            "id": "e5",
            "source": "review",
            "sourceHandle": "accept",
            "target": "output",
            "targetHandle": "result",
        },
        {
            "id": "e6",
            "source": "review",
            "sourceHandle": "refine",
            "target": "loop_guard",
            "targetHandle": "in",
        },
        {
            "id": "e7",
            "source": "review",
            "sourceHandle": "clarify",
            "target": "human_checkpoint",
            "targetHandle": "review",
        },
        {
            "id": "e8",
            "source": "human_checkpoint",
            "sourceHandle": "approve",
            "target": "output",
            "targetHandle": "result",
        },
        {
            "id": "e9",
            "source": "loop_guard",
            "sourceHandle": "loopBack",
            "target": "reasoning",
            "targetHandle": "task",
        },
        {
            "id": "e10",
            "source": "loop_guard",
            "sourceHandle": "exit",
            "target": "output",
            "targetHandle": "result",
        },
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


async def fake_llm_step(state, *, node_id, **kwargs):
    if node_id == "planning":
        return {"steps": ["s1"]}
    return {"answer": "4", "confidence": 0.9}


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
