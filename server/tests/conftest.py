"""공유 pytest fixture.

외부 LLM API에 의존하지 않는 빠른 테스트만 둔다 (AGENTS.md §6).
LLM 호출이 필요한 코드는 목(mock)으로 대체한다.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# server/ 를 import 경로에 추가 (main, manifests 등을 top-level로 import)
_SERVER_DIR = Path(__file__).resolve().parent.parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))


@pytest.fixture
def client() -> TestClient:
    """FastAPI 앱에 대한 동기 TestClient."""
    from main import app

    return TestClient(app)
