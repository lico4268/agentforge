"""Verify the shape of BUILTIN_MANIFESTS — no external dependencies."""

from manifests import BUILTIN_MANIFESTS


def test_each_manifest_has_required_fields():
    data = BUILTIN_MANIFESTS

    required = {"type", "runtime", "category", "label", "inputs", "outputs"}
    for node in data:
        missing = required - node.keys()
        assert not missing, f"{node.get('type')!r} manifest is missing keys: {missing}"
        assert isinstance(node["inputs"], list)
        assert isinstance(node["outputs"], list)


def test_manifest_types_are_unique():
    types = [n["type"] for n in BUILTIN_MANIFESTS]
    assert len(types) == len(set(types)), "duplicate node type present"


def test_loop_guard_manifest_declares_one_feedback_input_and_two_outputs():
    manifests = {n["type"]: n for n in BUILTIN_MANIFESTS}
    assert "loop.guard" in manifests, "loop.guard manifest is missing"

    loop = manifests["loop.guard"]
    assert loop["runtime"] == "loop_guard"
    assert loop["category"] == "policy"
    assert [(p["id"], p["label"]) for p in loop["inputs"]] == [("in", "Feedback")]
    assert [(p["id"], p["label"]) for p in loop["outputs"]] == [
        ("loopBack", "Loop back"),
        ("exit", "Exit"),
    ]


def test_loop_guard_manifest_exposes_all_five_guard_axes():
    manifests = {n["type"]: n for n in BUILTIN_MANIFESTS}
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
