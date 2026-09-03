"""ws_run → dispatch_graph → compile_graph 전체 경로를, 실제 arch.yaml 텍스트가
만드는 루프(가드 자동 삽입 포함) 그대로 통과시키는 통합 테스트. LLM은 목(AGENTS.md §6).

2026-09-02 텍스트 우선 전환(task 7) 이전에는 이 파일이 `ui/src/app/starterArchitecture.ts`
를 미러링하는 캔버스 JSON(`architecture`)을 썼다(옛 이름: test_ws_starter_graph.py). 그
캔버스 fixture는 review.intent와 함께 폐기됐지만, 이 파일이 지키던 주장 — "arch.yaml이
실제로 돈다, loop.guard가 실제로 예산을 소진시키고 exit로 빠진다, run이 WS로 끝까지
완주한다" — 은 전혀 안 죽었다. archfile.py가 만드는 arch.yaml 텍스트 fixture로 갈아
끼워 계속 검증한다.
"""

from fastapi.testclient import TestClient

import arch_files
import graphs.compile as compile_mod
import workspace as workspace_mod
from main import app

# input --> 풀이 --> 검토, 검토 -->|ok| output, 검토 -->|retry| 풀이(뒤로 가는 엣지) —
# archfile.py의 _insert_guards가 이 retry 엣지를 자동으로 loop.guard로 감싼다
# (DEFAULT_MAX_ITERATIONS=3, onExhaustion="exit"), 옛 스타터 그래프의
# maxIterations=3/onExhaustion=exit 설정과 동일한 예산.
LOOP_ARCH_YAML = """
name: loop test
flow: |
  input --> 풀이 --> 검토
  검토 -->|ok|    output
  검토 -->|retry| 풀이
nodes:
  풀이:
    in:  [task, feedback]
    out: [answer]
    prompt: 풀어라
  검토:
    in:  [task, answer]
    out: [feedback]
    prompt: 확인해라
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
    ws.send_json(
        {"kind": "run", "archFile": arch_file, "input": {"task": task}, "model": {}}
    )
    return _drain(ws)


def test_arch_file_loop_completes_over_the_websocket(tmp_path, monkeypatch):
    """루프를 한 번 돈 뒤 accept(ok)로 빠져나가 run_complete까지 도달한다."""
    (tmp_path / "loop.yaml").write_text(LOOP_ARCH_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    calls = {"검토": 0}

    async def fake_llm_step(state, *, node_id, **kwargs):
        if node_id == "풀이":
            return {"answer": "4"}
        if node_id == "검토":
            calls["검토"] += 1
            return {"feedback": "부족", "route": "retry"} if calls["검토"] == 1 else {
                "feedback": "ok",
                "route": "ok",
            }
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        events, outcome = _run(ws, "loop.yaml", "2+2")

    assert outcome["kind"] == "run_complete", outcome
    guard_events = [e for e in events if e.get("loopRuntime")]
    assert guard_events, "loop.guard 노드가 한 번도 실행되지 않았다"
    assert guard_events[0]["loopRuntime"]["iteration"] == 1
    assert "exitReason" not in guard_events[0]["loopRuntime"]


def test_arch_file_loop_exits_through_the_guard_when_iterations_run_out(tmp_path, monkeypatch):
    """검토가 끝없이 retry를 골라도 가드의 maxIterations(기본 3)가 exit 포트로
    강제 이탈시켜 run이 여전히 완주한다 — 영원히 돌지 않는다."""
    (tmp_path / "loop.yaml").write_text(LOOP_ARCH_YAML, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    monkeypatch.setattr(workspace_mod, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)

    async def always_retry(state, *, node_id, **kwargs):
        if node_id == "풀이":
            return {"answer": "4"}
        if node_id == "검토":
            return {"feedback": "부족", "route": "retry"}
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", always_retry)

    with TestClient(app) as client, client.websocket_connect("/ws/run") as ws:
        events, outcome = _run(ws, "loop.yaml", "2+2")

    assert outcome["kind"] == "run_complete", outcome
    guard_events = [e for e in events if e.get("loopRuntime")]
    assert [e["loopRuntime"]["iteration"] for e in guard_events] == [1, 2, 3, 4]
    assert guard_events[-1]["loopRuntime"]["exitReason"] == "maxIterations"
