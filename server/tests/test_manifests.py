"""GET /api/nodes 의 응답 형태 검증 — 외부 의존성 없음."""


def test_get_nodes_returns_manifest_list(client):
    resp = client.get("/api/nodes")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_each_manifest_has_required_fields(client):
    data = client.get("/api/nodes").json()

    # 프론트 manifest 스키마와의 계약: 모든 노드는 아래 키를 가진다.
    required = {"type", "runtime", "category", "label", "inputs", "outputs"}
    for node in data:
        missing = required - node.keys()
        assert not missing, f"{node.get('type')!r} 매니페스트에 누락된 키: {missing}"
        assert isinstance(node["inputs"], list)
        assert isinstance(node["outputs"], list)


def test_manifest_types_are_unique(client):
    types = [n["type"] for n in client.get("/api/nodes").json()]
    assert len(types) == len(set(types)), "중복된 노드 type 존재"


def test_loop_guard_manifest_declares_one_feedback_input_and_two_outputs(client):
    manifests = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert "loop.guard" in manifests, "loop.guard 매니페스트가 /api/nodes에 없다"

    loop = manifests["loop.guard"]
    assert loop["runtime"] == "loop_guard"
    assert loop["category"] == "policy"
    assert [(p["id"], p["label"]) for p in loop["inputs"]] == [("in", "Feedback")]
    assert [(p["id"], p["label"]) for p in loop["outputs"]] == [
        ("loopBack", "Loop back"),
        ("exit", "Exit"),
    ]


def test_loop_guard_manifest_exposes_all_five_guard_axes(client):
    manifests = {n["type"]: n for n in client.get("/api/nodes").json()}
    assert [c["key"] for c in manifests["loop.guard"]["config"]] == [
        "kind",
        "maxIterations",
        "maxTokens",
        "maxCostUsd",
        "maxDurationSec",
        "stuckWindow",
        "stuckThreshold",
        "onExhaustion",
    ]
