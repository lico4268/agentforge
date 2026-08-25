"""OpenRouter 즐겨찾기 파일 저장 + 캐시 라벨 조회. 카탈로그 fetch(네트워크)는 목 없이 테스트
하지 않는다 (AGENTS.md §6) — get_catalog()의 HTTP 부분은 REST 통합 테스트 범위 밖."""

import openrouter_catalog as orc


def test_favorites_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(orc, "FAVORITES_PATH", tmp_path / "favorites.json")
    assert orc.load_favorites() == orc.DEFAULT_FAVORITES


def test_save_then_load_favorites_dedupes_and_strips_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(orc, "FAVORITES_PATH", tmp_path / "favorites.json")
    saved = orc.save_favorites(["a/b", "c/d", "a/b", ""])
    assert saved == ["a/b", "c/d"]
    assert orc.load_favorites() == ["a/b", "c/d"]


def test_load_favorites_falls_back_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "favorites.json"
    path.write_text("not json")
    monkeypatch.setattr(orc, "FAVORITES_PATH", path)
    assert orc.load_favorites() == orc.DEFAULT_FAVORITES


def test_cached_label_falls_back_to_id_when_uncached(monkeypatch):
    monkeypatch.setattr(orc, "_catalog_cache", [])
    assert orc.cached_label("some/model") == "some/model"


def test_cached_label_uses_catalog_name_when_cached(monkeypatch):
    monkeypatch.setattr(orc, "_catalog_cache", [{"id": "some/model", "label": "Some Model"}])
    assert orc.cached_label("some/model") == "Some Model"


def test_favorites_roundtrip_and_models_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(orc, "FAVORITES_PATH", tmp_path / "favorites.json")

    put_resp = client.put("/api/openrouter/favorites", json=["x/y"])
    assert put_resp.status_code == 200
    assert put_resp.json() == ["x/y"]
    assert client.get("/api/openrouter/favorites").json() == ["x/y"]

    models = client.get("/api/models").json()
    favorite = next(m for m in models if m["id"] == "x/y")
    assert favorite["provider"] == "openrouter"
