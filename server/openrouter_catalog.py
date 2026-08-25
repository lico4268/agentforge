"""OpenRouter 라이브 모델 카탈로그 + 즐겨찾기.

OpenRouter는 모델이 수백 개라 전부 노출하면 노드 UI(Inspector 모델 슬롯)의
드롭다운이 못 쓸 정도로 길어진다. 그래서 전체 카탈로그는 별도 "즐겨찾기 선택"
화면에서만 브라우징하고, 실제 노드에서 고를 수 있는 목록은 즐겨찾기로 고정한
모델 id 몇 개뿐이다 (main.py:_load_models_config 참고).
"""

import json
import time
from pathlib import Path

import httpx

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CATALOG_TTL = 3600  # seconds — 키 불필요한 공개 엔드포인트라 부담 없이 캐시
FAVORITES_PATH = Path(__file__).parent / "openrouter_favorites.json"
DEFAULT_FAVORITES = ["openrouter/auto"]

_catalog_cache: list[dict] = []
_catalog_fetched_at: float = 0.0


async def get_catalog(force: bool = False) -> list[dict]:
    """OpenRouter 공개 모델 카탈로그. 메모리에 1시간 TTL로 캐시."""
    global _catalog_cache, _catalog_fetched_at
    if not force and _catalog_cache and time.monotonic() - _catalog_fetched_at < CATALOG_TTL:
        return _catalog_cache

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(CATALOG_URL)
        resp.raise_for_status()

    _catalog_cache = [
        {
            "id": m["id"],
            "label": m.get("name", m["id"]),
            "description": m.get("description", ""),
            "contextLength": m.get("context_length"),
        }
        for m in resp.json().get("data", [])
    ]
    _catalog_fetched_at = time.monotonic()
    return _catalog_cache


def cached_label(model_id: str) -> str:
    """카탈로그가 이미 로드돼 있으면 표시용 이름, 없으면 id 그대로. 네트워크 호출 없음."""
    for m in _catalog_cache:
        if m["id"] == model_id:
            return m["label"]
    return model_id


def load_favorites() -> list[str]:
    if not FAVORITES_PATH.exists():
        return list(DEFAULT_FAVORITES)
    try:
        return json.loads(FAVORITES_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_FAVORITES)


def save_favorites(ids: list[str]) -> list[str]:
    ids = [i for i in dict.fromkeys(ids) if i]  # 중복 제거 + 빈 문자열 제외, 순서 보존
    FAVORITES_PATH.write_text(json.dumps(ids, ensure_ascii=False, indent=2))
    return ids
