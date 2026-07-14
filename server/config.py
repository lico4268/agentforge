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
LLM_RETRY_COUNT: int = int(_get("execution.llm_retry_count", 1))
ESCALATE_TAGS: set[str] = set(_get("execution.escalate_tags", ["high-stakes", "medical", "legal"]))


# ── 모델 기본값 조회 ───────────────────────────────────────────────────────────────
def model_defaults(model_id: str) -> dict:
    """config.yaml models.list에서 해당 모델의 기본값 dict 반환.

    노드가 override하지 않은 설정(temperature/max_tokens/top_p)이 상속하는 토양.
    없는 모델이면 빈 dict. 키는 내부 snake_case (max_tokens 등).
    """
    for m in MODELS_LIST:
        if m.get("id") == model_id:
            return {
                k: v
                for k, v in {
                    "temperature": m.get("temperature"),
                    "max_tokens": m.get("max_tokens"),
                    "top_p": m.get("top_p"),
                }.items()
                if v is not None
            }
    return {}


# ── UI 기본값 ─────────────────────────────────────────────────────────────────────
UI_THEME: str = _get("ui.theme", "dark")
CANVAS_SNAP: bool = bool(_get("ui.canvas.snap_to_grid", True))
CANVAS_GRID_SIZE: int = int(_get("ui.canvas.grid_size", 20))
