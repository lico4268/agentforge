"""Integration test that passes the whole ws_run → dispatch_graph → compile_graph path through
the loop (including auto guard insertion) built from real arch.yaml text. The LLM is mocked
(AGENTS.md §6).

Before the 2026-09-02 text-first switch (task 7), this file used canvas JSON (`architecture`)
mirroring `ui/src/app/starterArchitecture.ts` (old name: test_ws_starter_graph.py). That
canvas fixture was retired along with review.intent, but the claims this file guarded — "arch.yaml
really runs, loop.guard really exhausts the budget and exits via exit, the run completes
end to end over WS" — never died. They are still verified by swapping in an arch.yaml
text fixture that archfile.py parses.
"""

from arch_samples import CHECKPOINT_YAML
from fastapi.testclient import TestClient

import arch_files
import graphs.compile as compile_mod
import main
import workspace as workspace_mod
from main import app
from workspace import read_run_record

# input --> solve --> review, review -->|ok| output, review -->|retry| solve (back edge) —
# archfile.py's _insert_guards automatically wraps this retry edge in a loop.guard
# (DEFAULT_MAX_ITERATIONS=3, onExhaustion="exit"), the same budget as the old starter graph's
# maxIterations=3/onExhaustion=exit setting.
LOOP_ARCH_YAML = """
name: loop test
flow: |
  input --> solve --> review
  review -->|ok|    output
  review -->|retry| solve
nodes:
  solve:
    in:  [task, feedback]
    out: [answer]
    prompt: Solve it
  review:
    in:  [task, answer]
    out: [feedback]
    prompt: Check it
"""


# item 4 — if the arch.yaml name: happens to equal a hardcoded fixed graph name,
# dispatch_graph ignores this file entirely and runs the fixed graph (baseline/treatment.py)
# instead. The deployed arch.yaml's name is "GSM8K Treatment", differing only in case,
# so a single rename falls into this trap.
RESERVED_NAME_ARCH_YAML = """
name: gsm8k-treatment
flow: |
  input --> solve --> output
nodes:
  solve:
    in:  [task]
    out: [answer]
    prompt: Solve it
"""


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


def _run(ws, arch_file: str, task: str) -> tuple[list[dict], dict]:
    ws.send_json({"kind": "run", "archFile": arch_file, "input": {"task": task}, "model": {}})
    return _drain(ws)


def test_arch_file_loop_completes_over_the_websocket(tmp_path, monkeypatch):
    """After going around the loop once, exit via accept (ok) and reach run_complete."""
    (tmp_path / "loop.yaml").write_text(LOOP_ARCH_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    calls = {"review": 0}

    async def fake_llm_step(state, *, node_id, **kwargs):
        if node_id == "solve":
            return {"answer": "4"}
        if node_id == "review":
            calls["review"] += 1
            return (
                {"feedback": "insufficient", "route": "retry"}
                if calls["review"] == 1
                else {
                    "feedback": "ok",
                    "route": "ok",
                }
            )
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        events, outcome = _run(ws, "loop.yaml", "2+2")

    assert outcome["kind"] == "run_complete", outcome
    guard_events = [e for e in events if e.get("loopRuntime")]
    assert guard_events, "loop.guard node never ran"
    assert guard_events[0]["loopRuntime"]["iteration"] == 1
    assert "exitReason" not in guard_events[0]["loopRuntime"]


def test_arch_file_loop_exits_through_the_guard_when_iterations_run_out(tmp_path, monkeypatch):
    """Even if review keeps picking retry forever, the guard's maxIterations (default 3) forces
    an exit through the exit port and the run still completes — it never loops forever."""
    (tmp_path / "loop.yaml").write_text(LOOP_ARCH_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    async def always_retry(state, *, node_id, **kwargs):
        if node_id == "solve":
            return {"answer": "4"}
        if node_id == "review":
            return {"feedback": "insufficient", "route": "retry"}
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", always_retry)

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        events, outcome = _run(ws, "loop.yaml", "2+2")

    assert outcome["kind"] == "run_complete", outcome
    guard_events = [e for e in events if e.get("loopRuntime")]
    assert [e["loopRuntime"]["iteration"] for e in guard_events] == [1, 2, 3, 4]
    assert guard_events[-1]["loopRuntime"]["exitReason"] == "maxIterations"


def test_arch_file_named_gsm8k_treatment_runs_its_own_graph_not_the_fixed_one(
    tmp_path, monkeypatch
):
    """Even if the arch.yaml name: equals the hardcoded fixed graph name ("gsm8k-treatment"),
    this file is a real arch.yaml with flow:, so it must compile as its own graph —
    dispatch_graph must not jump the queue to the fixed baseline/treatment.py by looking only at
    name (item 4).
    Confirmed by whether the node id ("solve"), absent from the fixed treatment graph, appears in
    the events."""
    (tmp_path / "reserved.yaml").write_text(RESERVED_NAME_ARCH_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    async def fake_llm_step(state, *, node_id, **kwargs):
        if node_id == "solve":
            return {"answer": "4"}
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        events, outcome = _run(ws, "reserved.yaml", "2+2")

    assert outcome["kind"] == "run_complete", outcome
    assert outcome["result"]["answer"] == "4"
    assert any(e["nodeId"] == "solve" for e in events)


def _recv_until(ws, kind: str) -> dict:
    while True:
        msg = ws.receive_json()
        if msg["kind"] == kind:
            return msg


def _gate_client_setup(tmp_path, monkeypatch):
    (tmp_path / "gate.yaml").write_text(CHECKPOINT_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)


def test_paused_run_resumes_after_server_restart(tmp_workspace, fake_llm, monkeypatch, tmp_path):
    _gate_client_setup(tmp_path, monkeypatch)
    with TestClient(app) as client:  # lifespan → SQLite checkpointer
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"kind": "run", "archFile": "gate.yaml", "input": {"task": "t"}})
            run_id = _recv_until(ws, "interrupt")["runId"]
        assert read_run_record(run_id)["status"] == "paused"
        main.active_runs.clear()  # simulate a restart: in-memory graph is gone
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"kind": "resume", "runId": run_id, "decision": {"action": "approve"}})
            assert _recv_until(ws, "run_complete")["runId"] == run_id
    assert read_run_record(run_id)["status"] == "done"


def test_resume_of_non_paused_run_after_restart_is_an_error(
    tmp_workspace, fake_llm, monkeypatch, tmp_path
):
    _gate_client_setup(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"kind": "run", "archFile": "gate.yaml", "input": {"task": "t"}})
            run_id = _recv_until(ws, "interrupt")["runId"]
            ws.send_json({"kind": "resume", "runId": run_id, "decision": {"action": "approve"}})
            _recv_until(ws, "run_complete")
        main.active_runs.clear()
        calls = len(fake_llm.calls)
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"kind": "resume", "runId": run_id, "decision": {"action": "approve"}})
            msg = _recv_until(ws, "error")
    assert "not paused" in msg["message"]
    assert len(fake_llm.calls) == calls
