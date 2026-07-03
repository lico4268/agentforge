"""workspace.py 단위 테스트 — write → list → read 왕복 (LLM mock 불필요한 순수 IO)."""

import pytest

import workspace as ws


@pytest.fixture(autouse=True)
def _temp_workspace(tmp_path, monkeypatch):
    """각 테스트마다 임시 WORKSPACE_DIR 사용."""
    monkeypatch.setattr(ws, "WORKSPACE_DIR", tmp_path / "workspace")
    yield


def test_write_string_output():
    """output이 문자열이면 본문으로 저장."""
    path = ws.write_node_output("run-1", "reasoning", "The answer is 42.")
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "# reasoning" in content
    assert "The answer is 42." in content


def test_write_dict_with_answer():
    """output dict에 answer 필드가 있으면 본문 + 메타 분리."""
    path = ws.write_node_output(
        "run-1",
        "output",
        {
            "answer": "The answer is **42**.",
            "confidence": 0.95,
        },
    )
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "# output" in content
    assert "The answer is **42**." in content
    assert "confidence" in content
    assert "0.95" in content


def test_write_dict_with_plan():
    """plan 필드도 본문으로 사용."""
    path = ws.write_node_output(
        "run-1",
        "planning",
        {
            "plan": ["Step 1", "Step 2"],
        },
    )
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "# planning" in content
    # plan이 list이므로 본문 추출 안 됨 → JSON 코드블록으로 저장
    assert "Step 1" in content


def test_write_none_returns_none():
    """output이 None이면 파일 생성 안 함."""
    path = ws.write_node_output("run-1", "planning", None)
    assert path is None


def test_list_run_files():
    """파일 목록 조회 — camelCase 키."""
    ws.write_node_output("run-1", "planning", {"plan": ["Step 1"]})
    ws.write_node_output("run-1", "reasoning", {"answer": "42"})

    files = ws.list_run_files("run-1")
    assert len(files) == 2
    assert all("name" in f and "nodeId" in f and "sizeBytes" in f for f in files)
    node_ids = [f["nodeId"] for f in files]
    assert "planning" in node_ids
    assert "reasoning" in node_ids


def test_list_empty_run():
    """존재하지 않는 run_id는 빈 목록."""
    files = ws.list_run_files("nonexistent-run")
    assert files == []


def test_read_run_file():
    """단일 파일 내용 읽기."""
    ws.write_node_output("run-1", "reasoning", {"answer": "42"})

    files = ws.list_run_files("run-1")
    assert len(files) == 1
    name = files[0]["name"]

    result = ws.read_run_file("run-1", name)
    assert result is not None
    assert result["name"] == name
    assert "# reasoning" in result["content"]
    assert "42" in result["content"]


def test_read_nonexistent_file():
    """없는 파일은 None."""
    result = ws.read_run_file("run-1", "nonexistent.md")
    assert result is None


def test_path_traversal_blocked():
    """경로 탈방지 시도는 None 반환."""
    ws.write_node_output("run-1", "reasoning", "test")
    result = ws.read_run_file("run-1", "../../../etc/passwd")
    assert result is None


def test_same_node_multiple_writes():
    """동일 노드 재실행 시 시퀀스 번호 증가."""
    ws.write_node_output("run-1", "reasoning", {"answer": "first"})
    ws.write_node_output("run-1", "reasoning", {"answer": "second"})

    files = ws.list_run_files("run-1")
    assert len(files) == 2
    # 시퀀스 번호가 다름
    names = sorted(f["name"] for f in files)
    assert names[0] < names[1]
