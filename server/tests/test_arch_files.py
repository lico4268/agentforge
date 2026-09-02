import pytest
from fastapi.testclient import TestClient

import arch_files
from main import app

SAMPLE = """
name: 샘플
flow: |
  input --> 풀이 --> output
nodes:
  풀이: { in: [task], out: [answer], prompt: 풀어라 }
"""


@pytest.fixture
def arch_dir(tmp_path, monkeypatch):
    (tmp_path / "sample.yaml").write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    return tmp_path


def test_list_arch_files(arch_dir):
    names = [f["name"] for f in arch_files.list_arch_files()]
    assert names == ["sample.yaml"]


def test_list_arch_files_skips_dangling_symlink(arch_dir):
    """stat()이 실패하는 항목(끊어진 심볼릭 링크) 하나 때문에 목록 전체가 500으로
    죽으면 안 된다 — 그 항목만 건너뛰고 나머지는 정상 반환해야 한다."""
    missing_target = arch_dir / "does_not_exist.yaml"
    (arch_dir / "dangling.yaml").symlink_to(missing_target)
    names = [f["name"] for f in arch_files.list_arch_files()]
    assert names == ["sample.yaml"]


def test_rest_list_skips_dangling_symlink(arch_dir):
    missing_target = arch_dir / "does_not_exist.yaml"
    (arch_dir / "dangling.yaml").symlink_to(missing_target)
    client = TestClient(app)
    resp = client.get("/api/arch")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "sample.yaml", "size": len(SAMPLE.encode("utf-8"))}]


def test_read_arch_file_returns_text_and_architecture(arch_dir):
    result = arch_files.read_arch_file("sample.yaml")
    assert result["name"] == "sample.yaml"
    assert "flow:" in result["text"]
    assert {n["id"] for n in result["architecture"]["nodes"]} == {"input", "풀이", "output"}
    assert result["warnings"] == []


def test_read_rejects_path_traversal(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("../../etc/passwd")


def test_read_rejects_absolute_path(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("/etc/passwd")


def test_read_treats_percent_encoded_slash_as_literal_filename(arch_dir):
    """읽는 함수 자체는 URL 디코딩을 하지 않는다 — "%2f"는 그냥 파일명의 일부
    문자열이다(실제 "/"가 아님). 진짜 위험은 ASGI/라우팅 계층에서 %2f가 실제
    "/"로 디코딩된 채로 여기 도달하는 경우인데, 그건 REST 레벨 테스트에서 확인한다
    (결론: Starlette str 컨버터는 디코딩된 "/"가 있으면 라우트 자체가 매치되지
    않아 여기 도달하기 전에 404로 막힌다)."""
    with pytest.raises(FileNotFoundError):
        arch_files.read_arch_file("a%2fb%2fpasswd")


def test_read_rejects_dot_only_name(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file(".")
    with pytest.raises(ValueError):
        arch_files.read_arch_file("..")


def test_read_rejects_null_byte(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("sample.yaml\x00.txt")


def test_read_rejects_symlink_escaping_arch_dir(arch_dir, tmp_path):
    outside = tmp_path.parent / "outside_secret.yaml"
    outside.write_text("name: secret\n", encoding="utf-8")
    (arch_dir / "escape.yaml").symlink_to(outside)
    with pytest.raises(ValueError):
        arch_files.read_arch_file("escape.yaml")


def test_read_missing_file_raises_file_not_found(arch_dir):
    with pytest.raises(FileNotFoundError):
        arch_files.read_arch_file("nope.yaml")


def test_rest_list_and_read(arch_dir):
    client = TestClient(app)
    assert client.get("/api/arch").json() == [
        {"name": "sample.yaml", "size": len(SAMPLE.encode("utf-8"))}
    ]
    body = client.get("/api/arch/sample.yaml").json()
    assert body["architecture"]["metadata"]["name"] == "샘플"


def test_rest_read_missing_file_404(arch_dir):
    client = TestClient(app)
    assert client.get("/api/arch/nope.yaml").status_code == 404


def test_rest_read_broken_yaml_400_with_line(arch_dir):
    (arch_dir / "broken.yaml").write_text(
        "flow: |\n  a --> ghost\nnodes:\n  a: { out: [x], prompt: p }\n", encoding="utf-8"
    )
    client = TestClient(app)
    resp = client.get("/api/arch/broken.yaml")
    assert resp.status_code == 400
    assert "ghost" in resp.json()["detail"]


def test_rest_read_yaml_syntax_error_400_not_500_with_line(arch_dir):
    """yaml.safe_load이 던지는 YAMLError(ValueError 아님)가 500으로 새지 않고,
    parse_arch 안에서 ArchError로 재포장되어 줄 번호와 함께 400으로 나오는지."""
    (arch_dir / "bad_syntax.yaml").write_text(
        "flow: |\n  a --> b\nnodes:\n  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n",
        encoding="utf-8",
    )
    client = TestClient(app)
    resp = client.get("/api/arch/bad_syntax.yaml")
    assert resp.status_code == 400
    assert "line 5" in resp.json()["detail"]


def test_ws_run_with_yaml_syntax_error_sends_clean_error_and_socket_stays_usable(arch_dir):
    """YAML 문법 오류가 있는 archFile을 돌리면 WS가 죽지 않고 error 메시지를 보내며,
    같은 소켓으로 이어지는 run이 정상 처리되는지."""
    (arch_dir / "bad_syntax.yaml").write_text(
        "flow: |\n  a --> b\nnodes:\n  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n",
        encoding="utf-8",
    )
    import main

    class FakeGraph:
        async def ainvoke(self, state0, config):
            return {"answer": "ok"}

    def fake_dispatch(architecture, model_cfg, emit, run_id):
        return FakeGraph()

    # monkeypatch 없이 fixture를 벗어나므로 직접 patch/undo
    original = main.dispatch_graph
    main.dispatch_graph = fake_dispatch
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json(
                {"kind": "run", "archFile": "bad_syntax.yaml", "input": {"task": "2+2"}}
            )
            msg = ws.receive_json()
            if msg["kind"] == "run_started":
                msg = ws.receive_json()
            assert msg["kind"] == "error"
            assert "line 5" in msg["message"]

            # 소켓이 죽지 않고 이어지는 run을 정상 처리하는지 확인
            ws.send_json({"kind": "run", "archFile": "sample.yaml", "input": {"task": "2+2"}})
            msg2 = ws.receive_json()
            if msg2["kind"] == "run_started":
                msg2 = ws.receive_json()
            assert msg2["kind"] == "run_complete"
    finally:
        main.dispatch_graph = original


def test_rest_percent_encoded_slash_blocked_at_routing_layer(arch_dir):
    """httpx가 %2f를 실제 "/"로 디코딩하면 Starlette의 str 경로 컨버터가 애초에
    라우트를 매치하지 않는다 — 우리 핸들러/`_resolve`에 도달하지도 못하고 일반
    404("Not Found")로 막힌다. 500으로 새지 않는지, 파일시스템에 닿지 않는지가
    핵심이라 200이 아니기만 하면 안전 — 여기서는 실제 관측값(404)을 고정한다."""
    client = TestClient(app)
    resp = client.get("/api/arch/..%2f..%2fetc%2fpasswd")
    assert resp.status_code == 404


def test_ws_run_accepts_arch_file_name(arch_dir, monkeypatch):
    """WS run 메시지가 architecture 대신 archFile로도 실행을 트리거할 수 있는지 —
    dispatch_graph에 넘어오는 architecture가 실제로 파일에서 파싱된 것인지 확인한다
    (LLM 호출은 dispatch_graph를 통째로 목킹해 피한다)."""
    import main

    captured = {}

    class FakeGraph:
        async def ainvoke(self, state0, config):
            return {"answer": "ok"}

    def fake_dispatch(architecture, model_cfg, emit, run_id):
        captured["architecture"] = architecture
        return FakeGraph()

    monkeypatch.setattr(main, "dispatch_graph", fake_dispatch)

    client = TestClient(app)
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({"kind": "run", "archFile": "sample.yaml", "input": {"task": "2+2"}})
        while True:
            msg = ws.receive_json()
            if msg["kind"] == "run_complete":
                break

    assert {n["id"] for n in captured["architecture"]["nodes"]} == {"input", "풀이", "output"}


def test_ws_run_with_missing_arch_file_sends_error(arch_dir):
    client = TestClient(app)
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({"kind": "run", "archFile": "nope.yaml", "input": {"task": "2+2"}})
        msg = ws.receive_json()
        if msg["kind"] == "run_started":
            msg = ws.receive_json()

    assert msg["kind"] == "error"
    assert "nope.yaml" in msg["message"]


def test_shipped_gsm8k_yaml_parses_and_compiles():
    """레포에 커밋된 실물 파일 — 문서와 코드가 어긋나면 여기서 잡힌다."""
    from pathlib import Path

    from archfile import parse_arch
    from graphs.compile import compile_graph

    async def _emit(_e):
        return None

    text = (Path(__file__).parent.parent / "arch" / "gsm8k.yaml").read_text(encoding="utf-8")
    arch, warnings = parse_arch(text)
    assert warnings == []
    assert compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _emit,
        "r1",
    ) is not None
