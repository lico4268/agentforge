import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# ── config.yaml 로드 ─────────────────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_raw: dict = (
    yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) if _CONFIG_PATH.exists() else {}
)


def _get(path: str, default=None):
    """점 경로로 중첩 키를 조회. 예: _get("execution.max_retries", 2)"""
    node = _raw
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part, default)
        if node is default:
            return default
    return node


# ── API 키 (.env 전용) ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")

# ── 서버 ─────────────────────────────────────────────────────────────────────────
SERVER_HOST: str = _get("server.host", "0.0.0.0")
SERVER_PORT: int = int(_get("server.port", 8000))
LOG_LEVEL: str = _get("server.log_level", "info")
CORS_ORIGINS: list[str] = _get("server.cors_origins", ["http://localhost:5173"])

# ── 모델 ─────────────────────────────────────────────────────────────────────────
DEFAULT_MODEL: str = _get("models.default", "claude-sonnet-4-6")
MODELS_LIST: list[dict] = _get("models.list", [])
PRICING: dict[str, dict] = _get("models.pricing", {}) or {}  # USD / 1M tokens {input, output}

# ── 로컬 모델 ─────────────────────────────────────────────────────────────────────
LOCAL_BASE_URL: str = os.getenv("LOCAL_BASE_URL") or _get(
    "local.base_url", "http://localhost:11434/v1"
)

# ── 실행 엔진 ─────────────────────────────────────────────────────────────────────
MAX_RETRIES: int = int(_get("execution.max_retries", 2))
NODE_TIMEOUT: int = int(_get("execution.node_timeout", 120))
ESCALATE_TAGS: set[str] = set(_get("execution.escalate_tags", ["high-stakes", "medical", "legal"]))

# ── UI 기본값 ─────────────────────────────────────────────────────────────────────
UI_THEME: str = _get("ui.theme", "dark")
CANVAS_SNAP: bool = bool(_get("ui.canvas.snap_to_grid", True))
CANVAS_GRID_SIZE: int = int(_get("ui.canvas.grid_size", 20))
