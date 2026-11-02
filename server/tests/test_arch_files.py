import pytest
from fastapi.testclient import TestClient

from web import arch_files
from web.main import app

SAMPLE = """
name: sample
flow: |
  input --> solve --> output
nodes:
  solve: { in: [task], out: [answer], prompt: Solve it }
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
    """A single entry on which stat() fails (a broken symlink) must not kill the whole list
    with a 500 — skip just that entry and return the rest normally."""
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
    assert {n["id"] for n in result["architecture"]["nodes"]} == {"input", "solve", "output"}
    assert result["warnings"] == []


def test_read_rejects_path_traversal(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("../../etc/passwd")


def test_read_rejects_absolute_path(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("/etc/passwd")


def test_read_treats_percent_encoded_slash_as_literal_filename(arch_dir):
    """The reading function itself does no URL decoding — "%2f" is just part of the filename
    string (not a real "/"). The real danger is %2f reaching here decoded into a real "/" by
    the ASGI/routing layer, which the REST-level test checks
    (conclusion: the Starlette str converter does not match the route at all if there is a
    decoded "/", so it is blocked with a 404 before reaching here)."""
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
    assert body["architecture"]["metadata"]["name"] == "sample"


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
    """Does the YAMLError thrown by yaml.safe_load (not a ValueError) avoid leaking as a 500, and
    instead get re-wrapped as ArchError inside parse_arch and come out as a 400 with a line
    number."""
    (arch_dir / "bad_syntax.yaml").write_text(
        "flow: |\n  a --> b\nnodes:\n  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n",
        encoding="utf-8",
    )
    client = TestClient(app)
    resp = client.get("/api/arch/bad_syntax.yaml")
    assert resp.status_code == 400
    assert "line 5" in resp.json()["detail"]


def test_ws_run_with_yaml_syntax_error_sends_clean_error_and_socket_stays_usable(
    arch_dir, tmp_workspace, fake_llm
):
    """When running an archFile with a YAML syntax error, does the WS stay alive and send an error
    message, and does a following run on the same socket get handled normally."""
    (arch_dir / "bad_syntax.yaml").write_text(
        "flow: |\n  a --> b\nnodes:\n  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n",
        encoding="utf-8",
    )
    client = TestClient(app)
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({"kind": "run", "archFile": "bad_syntax.yaml", "input": {"task": "2+2"}})
        msg = ws.receive_json()
        if msg["kind"] == "run_started":
            msg = ws.receive_json()
        assert msg["kind"] == "error"
        assert "line 5" in msg["message"]

        # Verify that the socket stays alive and handles the following run normally
        ws.send_json({"kind": "run", "archFile": "sample.yaml", "input": {"task": "2+2"}})
        while (msg2 := ws.receive_json())["kind"] in ("run_started", "event"):
            pass
        assert msg2["kind"] == "run_complete"


def test_rest_percent_encoded_slash_blocked_at_routing_layer(arch_dir):
    """If httpx decodes %2f into a real "/", Starlette's str path converter doesn't match
    the route at all — it never reaches our handler/`_resolve` and is blocked with a generic
    404 ("Not Found"). The point is that it doesn't leak a 500 and doesn't touch the filesystem,
    so anything other than 200 is safe — here we pin the actually observed value (404)."""
    client = TestClient(app)
    resp = client.get("/api/arch/..%2f..%2fetc%2fpasswd")
    assert resp.status_code == 404


def test_ws_run_accepts_arch_file_name(arch_dir, tmp_workspace, fake_llm):
    """A WS run message names a server/arch/*.yaml file, and that file's nodes are what run."""
    client = TestClient(app)
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({"kind": "run", "archFile": "sample.yaml", "input": {"task": "2+2"}})
        while ws.receive_json()["kind"] != "run_complete":
            pass

    assert fake_llm.calls == ["solve"]


def test_ws_run_with_missing_arch_file_sends_error(arch_dir):
    client = TestClient(app)
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({"kind": "run", "archFile": "nope.yaml", "input": {"task": "2+2"}})
        msg = ws.receive_json()
        if msg["kind"] == "run_started":
            msg = ws.receive_json()

    assert msg["kind"] == "error"
    assert "nope.yaml" in msg["message"]


def test_shipped_gsm8k_yaml_parses_and_compiles(monkeypatch):
    """A real file committed to the repo — mismatch between docs and code is caught here."""
    from pathlib import Path

    from archfile import parse_arch
    from graphs.compile import compile_graph

    monkeypatch.setattr("graphs.compile.build_model", lambda s: None)

    async def _emit(_e):
        return None

    text = (Path(__file__).parent.parent / "arch" / "gsm8k.yaml").read_text(encoding="utf-8")
    arch, warnings = parse_arch(text)
    assert warnings == []
    assert (
        compile_graph(
            arch,
            {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
            _emit,
            "r1",
        )
        is not None
    )


def test_shipped_arch_files_compile(monkeypatch):
    """Every example in server/arch/ must pass `agentforge check`."""
    import cli

    monkeypatch.setattr("graphs.compile.build_model", lambda s: None)

    for path in sorted(arch_files.ARCH_DIR.glob("*.yaml")):
        assert cli.main(["check", str(path)]) == 0, path.name
