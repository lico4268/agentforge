"""Shared pytest fixtures.

Only fast tests that don't depend on external LLM APIs live here (AGENTS.md §6).
Code that needs LLM calls is replaced with mocks.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add server/ to the import path (so main, manifests, etc. can be imported as top-level)
_SERVER_DIR = Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))


@pytest.fixture
def client() -> TestClient:
    """Synchronous TestClient for the FastAPI app."""
    from main import app

    return TestClient(app)


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch) -> Path:
    """Redirect workspace.WORKSPACE_DIR to a temp dir (read at call time by workspace functions)."""
    import workspace

    path = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "WORKSPACE_DIR", path)
    return path


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model + run_llm_step in graphs.compile; no network."""
    from types import SimpleNamespace

    import graphs.compile as gc
    from events import make_event

    fake = SimpleNamespace(fail=set(), calls=[])

    async def _run(state, *, node_id, output_model, emit, run_id, **kwargs):
        fake.calls.append(node_id)
        if node_id in fake.fail:
            raise RuntimeError("boom")
        usage = {"prompt": 10, "completion": 5, "total_tokens": 15, "cost": 0.001, "model": "fake"}
        await emit(make_event(run_id, node_id, "log", token_usage=usage))
        return {f: f"{node_id}:{f}" for f in output_model.model_fields}

    monkeypatch.setattr(gc, "build_model", lambda s: None)
    monkeypatch.setattr(gc, "run_llm_step", _run)
    return fake
