"""Live OpenRouter model catalog + favorites.

OpenRouter has hundreds of models, so exposing them all would make the node UI's
(Inspector model slot) dropdown unusably long. The full catalog is therefore browsed only in a
"pick favorites" screen, and the list selectable on actual nodes is just the few
model ids pinned as favorites (see web/main.py:_load_models_config).
"""

import json
import time
from pathlib import Path

import httpx

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CATALOG_TTL = 3600  # seconds — public endpoint needing no key, so caching is cheap
FAVORITES_PATH = Path(__file__).parent.parent / "openrouter_favorites.json"
DEFAULT_FAVORITES = ["openrouter/auto"]

_catalog_cache: list[dict] = []
_catalog_fetched_at: float = 0.0


async def get_catalog(force: bool = False) -> list[dict]:
    """OpenRouter public model catalog. Cached in memory with a 1-hour TTL."""
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
    """Display name if the catalog is already loaded, otherwise the id as-is. No network call."""
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
    ids = [i for i in dict.fromkeys(ids) if i]  # dedupe + drop empty strings, preserve order
    FAVORITES_PATH.write_text(json.dumps(ids, ensure_ascii=False, indent=2))
    return ids
