"""Unit tests for workspace.py — write → list → read round trip (pure IO, no LLM mock needed)."""

import pytest

import workspace as ws


@pytest.fixture(autouse=True)
def _temp_workspace(tmp_path, monkeypatch):
    """Use a temporary WORKSPACE_DIR for each test."""
    monkeypatch.setattr(ws, "WORKSPACE_DIR", tmp_path / "workspace")
    yield


def test_write_string_output():
    """If output is a string, save it as the body."""
    path = ws.write_node_output("run-1", "reasoning", "The answer is 42.")
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "# reasoning" in content
    assert "The answer is 42." in content


def test_write_dict_with_answer():
    """If the output dict has an answer field, split into body + metadata."""
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
    """The plan field is also used as the body."""
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
    # plan is a list, so no body is extracted → saved as a JSON code block
    assert "Step 1" in content


def test_write_none_returns_none():
    """If output is None, no file is created."""
    path = ws.write_node_output("run-1", "planning", None)
    assert path is None


def test_list_run_files():
    """List files — camelCase keys."""
    ws.write_node_output("run-1", "planning", {"plan": ["Step 1"]})
    ws.write_node_output("run-1", "reasoning", {"answer": "42"})

    files = ws.list_run_files("run-1")
    assert len(files) == 2
    assert all("name" in f and "nodeId" in f and "sizeBytes" in f for f in files)
    node_ids = [f["nodeId"] for f in files]
    assert "planning" in node_ids
    assert "reasoning" in node_ids


def test_list_empty_run():
    """A nonexistent run_id yields an empty list."""
    files = ws.list_run_files("nonexistent-run")
    assert files == []


def test_read_run_file():
    """Read a single file's content."""
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
    """A missing file yields None."""
    result = ws.read_run_file("run-1", "nonexistent.md")
    assert result is None


def test_path_traversal_blocked():
    """A path traversal attempt returns None."""
    ws.write_node_output("run-1", "reasoning", "test")
    result = ws.read_run_file("run-1", "../../../etc/passwd")
    assert result is None


def test_same_node_multiple_writes():
    """Re-running the same node increments the sequence number."""
    ws.write_node_output("run-1", "reasoning", {"answer": "first"})
    ws.write_node_output("run-1", "reasoning", {"answer": "second"})

    files = ws.list_run_files("run-1")
    assert len(files) == 2
    # sequence numbers differ
    names = sorted(f["name"] for f in files)
    assert names[0] < names[1]
