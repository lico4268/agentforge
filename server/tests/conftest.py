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
