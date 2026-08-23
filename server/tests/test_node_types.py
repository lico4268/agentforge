"""server/node_types.py — 커스텀 노드 타입 파일 저장소 + REST 엔드포인트 테스트.

Phase B③: BUILTIN_MANIFESTS(파이썬 하드코딩, 7개 런타임의 실행 로직과 묶임)는
안 건드리고, 그 7개 런타임 중 하나를 골라 쓰는 사용자 정의 매니페스트만
server/node_types/<type>.json에 저장한다.
"""

import pytest
from pydantic import ValidationError

import node_types as nt


@pytest.fixture(autouse=True)
def _isolate_node_types_dir(tmp_path, monkeypatch):
    """실제 server/node_types/를 건드리지 않도록 매 테스트마다 임시 디렉토리로 교체."""
    monkeypatch.setattr(nt, "NODE_TYPES_DIR", tmp_path)


def _manifest(**overrides) -> dict:
    base = {
        "type": "custom.summarizer",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Summarizer",
        "inputs": [{"id": "text", "label": "Text", "dataType": "text", "required": True}],
        "outputs": [{"id": "summary", "label": "Summary", "dataType": "text"}],
        "defaults": {"outputSchema": {"summary": "string"}},
    }
    base.update(overrides)
    return base


def test_save_and_list_round_trips_a_custom_manifest():
    manifest = nt.NodeTypeManifest(**_manifest())
    saved = nt.save_custom_manifest(manifest)
    assert saved["type"] == "custom.summarizer"
    assert nt.list_custom_manifests() == [saved]


def test_save_overwrites_existing_manifest_with_same_type():
    nt.save_custom_manifest(nt.NodeTypeManifest(**_manifest(label="v1")))
    nt.save_custom_manifest(nt.NodeTypeManifest(**_manifest(label="v2")))
    manifests = nt.list_custom_manifests()
    assert len(manifests) == 1
    assert manifests[0]["label"] == "v2"


def test_delete_removes_a_saved_manifest():
    nt.save_custom_manifest(nt.NodeTypeManifest(**_manifest()))
    assert nt.delete_custom_manifest("custom.summarizer") is True
    assert nt.list_custom_manifests() == []


def test_delete_returns_false_for_unknown_type():
    assert nt.delete_custom_manifest("does.not.exist") is False


def test_manifest_rejects_unknown_runtime():
    with pytest.raises(ValidationError, match="unknown runtime"):
        nt.NodeTypeManifest(**_manifest(runtime="not_a_runtime"))


def test_manifest_rejects_unknown_category():
    with pytest.raises(ValidationError, match="unknown category"):
        nt.NodeTypeManifest(**_manifest(category="not_a_category"))


def test_manifest_rejects_type_that_shadows_a_builtin():
    with pytest.raises(ValidationError, match="built-in"):
        nt.NodeTypeManifest(**_manifest(type="planning.decompose"))


# ─── REST 엔드포인트 ───────────────────────────────────────────────────────────


def test_post_node_types_creates_and_get_nodes_includes_it(client):
    resp = client.post("/api/node-types", json=_manifest())
    assert resp.status_code == 200
    assert resp.json()["type"] == "custom.summarizer"

    types = {m["type"] for m in client.get("/api/nodes").json()}
    assert "custom.summarizer" in types
    assert "planning.decompose" in types  # builtin은 그대로 함께 나온다


def test_post_node_types_rejects_invalid_manifest_with_422(client):
    resp = client.post("/api/node-types", json=_manifest(runtime="not_a_runtime"))
    assert resp.status_code == 422


def test_get_node_types_lists_only_custom_manifests(client):
    client.post("/api/node-types", json=_manifest())
    resp = client.get("/api/node-types")
    assert resp.status_code == 200
    assert [m["type"] for m in resp.json()] == ["custom.summarizer"]


def test_delete_node_types_removes_it(client):
    client.post("/api/node-types", json=_manifest())
    resp = client.delete("/api/node-types/custom.summarizer")
    assert resp.status_code == 200
    assert client.get("/api/node-types").json() == []


def test_delete_node_types_404_for_unknown_type(client):
    resp = client.delete("/api/node-types/does.not.exist")
    assert resp.status_code == 404
