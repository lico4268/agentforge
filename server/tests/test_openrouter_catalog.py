"""OpenRouter favorites file storage + cached label lookup. The catalog fetch (network) is
not tested without a mock (AGENTS.md §6) — get_catalog()'s HTTP part is out of scope here."""

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
