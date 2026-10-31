import pytest
from arch_samples import CHECKPOINT_YAML, FAN_IN, THREE_YAML

from archfile import parse_arch
from replay import ReplayError, changed_nodes, pick_from, reuse_stats, visit_order


def _ev(t, n, **kw):
    return {"eventType": t, "nodeId": n, **kw}


def _arch(text):
    return parse_arch(text)[0]


def test_prompt_edit_is_a_spec_change():
    new = _arch(THREE_YAML.replace("prompt: pb", "prompt: NEW"))
    assert changed_nodes(_arch(THREE_YAML), new) == {"b"}


def test_model_and_temperature_edits_are_spec_changes():
    old = _arch(THREE_YAML)
    m = _arch(THREE_YAML.replace("prompt: pb}", "prompt: pb, model: anthropic/x}"))
    t = _arch(THREE_YAML.replace("prompt: pb}", "prompt: pb, temperature: 0.5}"))
    assert changed_nodes(old, m) == {"b"} and changed_nodes(old, t) == {"b"}


def test_rewired_flow_refused():
    text = (
        THREE_YAML.replace("a --> b --> c", "a --> c")
        .replace("  b: {in: [x], out: [y], prompt: pb}\n", "")
        .replace("in: [y]", "in: [x]")
    )
    with pytest.raises(ReplayError, match="flow changed — run it fresh"):
        changed_nodes(_arch(THREE_YAML), _arch(text))


def test_checkpoint_label_change_refused():
    new = _arch(CHECKPOINT_YAML.replace("|reject|", "|no|"))
    with pytest.raises(ReplayError, match="flow changed"):
        changed_nodes(_arch(CHECKPOINT_YAML), new)


def test_visit_order_first_visits_with_reused_prefix():
    evs = [_ev("node_start", "b"), _ev("node_start", "c"), _ev("node_start", "b")]
    assert visit_order(evs, ["a"]) == ["a", "b", "c"]


def _pick(changed_prompts, order, from_node):
    text = THREE_YAML
    for n in changed_prompts:
        text = text.replace(f"prompt: p{n}", "prompt: NEW")
    return pick_from(_arch(THREE_YAML), _arch(text), order, from_node)


def test_auto_from_picks_first_changed_in_run_order():
    assert _pick("ac", ["a", "b", "c"], None) == "a"


def test_auto_from_nothing_changed_refused():
    with pytest.raises(ReplayError, match="no node changed — pass --from <node>"):
        _pick("", ["a", "b", "c"], None)


def test_changed_node_not_run_in_parent_refused():
    with pytest.raises(ReplayError, match="node 'b' changed but never ran in the parent"):
        _pick("b", ["a"], None)


def test_explicit_from_with_upstream_change_refused():
    with pytest.raises(ReplayError, match="upstream node 'a' changed — replay from 'a' instead"):
        _pick("a", ["a", "b", "c"], "b")


def test_explicit_from_downstream_change_ok():
    assert _pick("c", ["a", "b", "c"], "b") == "b"


def test_explicit_from_not_run_refused():
    with pytest.raises(ReplayError, match="node 'zzz' did not run in the parent"):
        _pick("c", ["a", "b", "c"], "zzz")


def test_reuse_stats_counts_prefix_cost():
    evs = [
        _ev("node_start", "input"),
        _ev("node_start", "a"),
        _ev("log", "a", tokenUsage={"cost": 0.25}),
        _ev("node_end", "a"),
        _ev("node_start", "b"),
        _ev("log", "b", tokenUsage={"cost": 1.0}),
    ]
    assert reuse_stats(evs, "b", ("b",), {"input"}) == (["a"], 0.25)


def test_reuse_stats_excludes_siblings_in_next():
    evs = [
        _ev("node_start", "a"),
        _ev("node_start", "b"),
        _ev("log", "a", tokenUsage={"cost": 0.5}),
    ]
    assert reuse_stats(evs, "b", ("a", "b"), set()) == ([], 0.0)


def test_join_mode_edit_is_a_flow_change():
    old = _arch(FAN_IN % ", join: all")
    new = _arch(FAN_IN % ", join: any")
    with pytest.raises(ReplayError, match="flow changed"):
        changed_nodes(old, new)
