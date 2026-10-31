"""Decide which node a replay starts from, and what it reuses from the parent run."""

import json

from archfile import USER_NODE_TYPE


class ReplayError(Exception):
    """Message goes to the user as-is."""


def _spec(node: dict) -> dict:
    return {k: v for k, v in node.items() if k != "position"}


def _flow(arch: dict) -> tuple:
    nodes = arch["nodes"]
    # joinMode is topology in compile_graph, so it belongs to the flow
    ids = sorted((n["id"], n["type"], n.get("joinMode")) for n in nodes)
    edges = sorted(
        json.dumps({k: v for k, v in e.items() if k != "id"}, sort_keys=True) for e in arch["edges"]
    )
    fixed = sorted(
        json.dumps(_spec(n), sort_keys=True) for n in nodes if n["type"] != USER_NODE_TYPE
    )
    return ids, edges, fixed


def changed_nodes(old: dict, new: dict) -> set[str]:
    if _flow(old) != _flow(new):
        raise ReplayError("flow changed — run it fresh")
    old_by_id = {n["id"]: n for n in old["nodes"]}
    return {
        n["id"]
        for n in new["nodes"]
        if n["type"] == USER_NODE_TYPE and _spec(n) != _spec(old_by_id[n["id"]])
    }


def _first_visits(events: list[dict]) -> list[str]:
    return list(dict.fromkeys(e["nodeId"] for e in events if e["eventType"] == "node_start"))


def visit_order(events: list[dict], reused: list[str]) -> list[str]:
    return list(dict.fromkeys([*reused, *_first_visits(events)]))


def pick_from(old: dict, new: dict, order: list[str], from_node: str | None) -> str:
    changed = changed_nodes(old, new)
    if from_node is None:
        if not changed:
            raise ReplayError("no node changed — pass --from <node>")
        for n in order:
            if n in changed:
                return n
        n = sorted(changed)[0]
        raise ReplayError(f"node '{n}' changed but never ran in the parent — run it fresh")
    if from_node not in order:
        raise ReplayError(f"node '{from_node}' did not run in the parent")
    for u in order[: order.index(from_node)]:
        if u in changed:
            raise ReplayError(f"upstream node '{u}' changed — replay from '{u}' instead")
    return from_node


def reuse_stats(
    events: list[dict], from_node: str, next_nodes: tuple[str, ...], hidden: set[str]
) -> tuple[list[str], float]:
    """Nodes (first-visit order) and cost the replay reuses from before `from_node` started.

    The cut sits at the earliest start among `next_nodes` seen up to from_node's first
    start, so fanout siblings of from_node are not counted as reused."""
    first = next(
        i
        for i, e in enumerate(events)
        if e["eventType"] == "node_start" and e["nodeId"] == from_node
    )
    head = events[: first + 1]
    cuts = [
        max(i for i, e in enumerate(head) if e["eventType"] == "node_start" and e["nodeId"] == n)
        for n in next_nodes
        if any(e["eventType"] == "node_start" and e["nodeId"] == n for e in head)
    ]
    prefix = events[: min(cuts)]
    nodes = [n for n in _first_visits(prefix) if n not in hidden]
    cost = sum(
        e["tokenUsage"].get("cost", 0.0)
        for e in prefix
        if e["eventType"] == "log" and e.get("tokenUsage")
    )
    return nodes, cost
