"""
compile_graph: compiles an Architecture (dict) serialized from the canvas into an
executable LangGraph StateGraph. This is the v0.3 seam that replaces the v0.1 fixed-graph
(baseline.py/treatment.py) dispatch — dispatch_graph falls back here for any architecture
name other than 'gsm8k-baseline'/'gsm8k-treatment'.
"""

import time
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, create_model

import config
from events import EventEmitter, make_event
from manifests import BUILTIN_MANIFESTS
from models import CallPolicy, ModelSettings, build_model
from nodes.checkpoint import make_human_checkpoint
from nodes.llm_step import run_llm_step
from nodes.loop_guard import evaluate_loop_guard, next_runtime
from state import AgentState, read_state_value, write_state_value

MANIFESTS_BY_TYPE = {m["type"]: m for m in BUILTIN_MANIFESTS}

# Manifest defaults.outputSchema tag -> Pydantic field type. Nested objects (like review.intent's
# ReviewDelta) cannot be expressed in this flat tag format, so they are intentionally unsupported —
# the review runtime skips this dynamic-generation path and uses its own hardcoded model.
_OUTPUT_SCHEMA_TYPES: dict[str, Any] = {
    "string": str,
    "number": float,
    "boolean": bool,
    "string[]": list[str],
    "number[]": list[float],
}


def _build_output_model(node_type: str, output_schema: dict[str, Any]) -> type[BaseModel]:
    """Builds the Pydantic model for structured output on the fly from an llm_step node
    manifest's defaults.outputSchema. Previously, hand-written classes such as
    PlanOut/ReasonOut were hardcoded per node type in LLM_STEP_TABLE — which forced an
    edit to this file every time a new llm_step type was created in the canvas/Inspector.
    Now the manifest alone is enough.

    A list-valued schema entry is a branch node's route field — treated as Literal[...]
    so the LLM can emit only one of those labels (design §5).
    """
    fields: dict[str, Any] = {}
    for key, tag in output_schema.items():
        if isinstance(tag, list):
            fields[key] = (Literal[tuple(tag)], ...)
        else:
            fields[key] = (_OUTPUT_SCHEMA_TYPES[tag], ...)
    name_parts = node_type.replace(".", "_").split("_")
    model_name = "".join(part.capitalize() for part in name_parts) + "Out"
    return create_model(model_name, **fields)


def _effective_output_schema(
    node: dict, manifest: dict, branch_labels: list[str] | None = None
) -> dict[str, Any]:
    """The outputSchema this node instance will actually use — the manifest's if it declares
    one, otherwise (Phase B④: a type with a completely empty manifest, like custom.node)
    derived on the fly from this instance's config.outputs ports (all treated as string —
    matches the Inspector UI decision that ports carry only a label, no type).

    If branch_labels is given, this node is a branch node (design §5) — a route field is
    added to the schema. Its value is the label list as-is, and _build_output_model turns
    it into a Literal."""
    defaults = manifest.get("defaults") or {}
    output_schema = dict(defaults.get("outputSchema") or {})
    if not output_schema:
        config = node.get("config") or {}
        output_ports = config.get("outputs") or manifest.get("outputs") or []
        output_schema = {p["id"]: "string" for p in output_ports}
    if branch_labels:
        output_schema["route"] = branch_labels
    return output_schema


def _output_write_keys(node: dict, manifest: dict) -> list[str]:
    """The AgentState keys this llm_step node actually writes — the outputSchema keys
    remapped through defaults.outputKeyMap (key name unchanged if unmapped). Replaces the
    old hardcoded LLM_STEP_TABLE "writes" field — `_validate_required_inputs` still uses it."""
    defaults = manifest.get("defaults") or {}
    key_map = defaults.get("outputKeyMap") or {}
    return [key_map.get(key, key) for key in _effective_output_schema(node, manifest)]


def _llm_step_spec(
    node: dict, manifest: dict, branch_labels: list[str] | None = None
) -> dict[str, Any]:
    """Derives everything needed to run an llm_step node from the manifest defaults
    (+ Phase B④: the instance config) — output_model (dynamic Pydantic model),
    extra_inputs (inputs read directly from state that have no port), writes, and
    key_map (LLM output field name -> AgentState key, declared via outputKeyMap when
    they differ).

    If branch_labels is given, this node is a branch node — a route field is added to
    the schema and key_map is extended so each node writes to its own state key
    (__route__<id>). That way multiple branch nodes never overwrite each other's route
    value.
    """
    defaults = manifest.get("defaults") or {}
    output_schema = _effective_output_schema(node, manifest, branch_labels)
    key_map = defaults.get("outputKeyMap") or {}
    if branch_labels:
        key_map = {**key_map, "route": f"__route__{node['id']}"}
    extra_inputs = [(f["id"], f["label"]) for f in defaults.get("extraInputs") or []]
    return {
        "output_model": _build_output_model(node["type"], output_schema),
        "extra_inputs": extra_inputs,
        "writes": [key_map.get(k, k) for k in output_schema],
        "key_map": key_map,
    }


PASSTHROUGH_TYPES = {"io.input", "io.output", "model.binding"}


def _make_passthrough_node(
    node_id: str,
    node_type: str,
    node_config: dict,
    emit: EventEmitter,
    run_id: str,
):
    async def passthrough(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        output = None
        updates: dict = {}
        if node_type == "io.input":
            submitted_task = state.get("task")
            sample = node_config.get("sample")
            effective_task = submitted_task or sample
            if not submitted_task and sample:
                updates["task"] = sample
            output = {"task": effective_task}
        elif node_type == "io.output":
            output = {"answer": state.get("answer"), "review": state.get("review_delta")}
        await emit(make_event(run_id, node_id, "node_end", output=output))
        return updates

    return passthrough


def _resolve_model(node: dict, default_model_cfg: dict):
    """Resolves slot override -> model default (config.yaml) -> global default, in that order,
    and returns (BaseChatModel, CallPolicy). Only modelSlots[0] is used as the run model
    (current limitation).
    """
    slots = (node.get("config") or {}).get("modelSlots") or []
    slot = slots[0] if slots else None
    if slot:
        settings, policy = _settings_from_slot(slot)
    else:
        settings, policy = _settings_from_default(default_model_cfg)
    return build_model(settings), policy


def _coalesce(*vals):
    """First non-None value. (Note: 0/False are valid values, so only a None check is made.)"""
    for v in vals:
        if v is not None:
            return v
    return None


def _coerce_int(*vals) -> int | None:
    for v in vals:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return None


def _coerce_float(*vals) -> float | None:
    for v in vals:
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def _fallback_settings(fb: dict | None) -> ModelSettings | None:
    if not fb or not fb.get("model"):
        return None
    return ModelSettings(
        provider=fb.get("provider", "google"),
        model=fb["model"],
        temperature=float(_coerce_float(fb.get("temperature"), 0.0) or 0.0),
    )


def _settings_from_slot(slot: dict) -> tuple[ModelSettings, CallPolicy]:
    provider = slot["provider"]
    model = slot["model"]
    md = config.model_defaults(model)
    settings = ModelSettings(
        provider=provider,
        model=model,
        temperature=float(_coerce_float(slot.get("temperature"), md.get("temperature"), 0.0)),
        max_tokens=_coerce_int(slot.get("maxTokens"), md.get("max_tokens")),
        top_p=_coerce_float(slot.get("topP"), md.get("top_p")),
        stop=[s for s in (slot.get("stopSequences") or []) if s] or None,
        seed=_coerce_int(slot.get("seed")),
    )
    policy = CallPolicy(
        timeout_seconds=float(_coerce_float(slot.get("timeoutSeconds"), config.NODE_TIMEOUT)),
        retry_count=int(_coerce_int(slot.get("retryCount"), config.LLM_RETRY_COUNT)),
        fallback=_fallback_settings(slot.get("fallback")),
    )
    return settings, policy


def _settings_from_default(cfg: dict) -> tuple[ModelSettings, CallPolicy]:
    provider = cfg["provider"]
    model = cfg["model"]
    md = config.model_defaults(model)
    settings = ModelSettings(
        provider=provider,
        model=model,
        temperature=float(_coerce_float(cfg.get("temperature"), md.get("temperature"), 0.0)),
        max_tokens=md.get("max_tokens"),
        top_p=md.get("top_p"),
        stop=None,
        seed=None,
    )
    policy = CallPolicy(timeout_seconds=config.NODE_TIMEOUT, retry_count=config.LLM_RETRY_COUNT)
    return settings, policy


def _make_llm_step_node(
    node: dict,
    manifest: dict,
    model,
    policy: CallPolicy,
    emit: EventEmitter,
    run_id: str,
    loop_policy_ids: list[str] | None = None,
    branch_labels: list[str] | None = None,
):
    node_id = node["id"]
    spec = _llm_step_spec(node, manifest, branch_labels)
    key_map = spec["key_map"]
    node_config = node.get("config") or {}
    system_prompt = node_config.get("systemPrompt") or manifest.get("defaults", {}).get(
        "systemPrompt", ""
    )
    # Phase B④: for types with no input ports in the manifest (like custom.node), derive
    # them on the fly from this instance's config.inputs — other types never fill
    # config.inputs, so manifest["inputs"] is used as-is (no change).
    input_ports = node_config.get("inputs") or manifest["inputs"]
    input_keys = [(p["id"], p["label"]) for p in input_ports] + spec["extra_inputs"]
    policy_ids = loop_policy_ids or []

    async def step(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        usage: dict = {}
        result = await run_llm_step(
            state,
            node_id=node_id,
            system_prompt=system_prompt,
            input_keys=input_keys,
            output_model=spec["output_model"],
            model=model,
            emit=emit,
            run_id=run_id,
            call_policy=policy,
            usage_sink=usage,
        )
        output = {key_map.get(key, key): value for key, value in result.items()}
        updates: dict = {}
        for key, value in output.items():
            write_state_value(updates, key, value)
        if policy_ids and usage:
            updates["loop_runtime"] = {
                pid: {
                    "total_tokens": usage.get("prompt", 0) + usage.get("completion", 0),
                    "total_cost_usd": usage.get("cost", 0.0),
                }
                for pid in policy_ids
            }
        await emit(make_event(run_id, node_id, "node_end", output=output))
        return updates

    return step


def _filter_control_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """io.input is a virtual node that completes immediately, so it can fan out to several
    targets at once; if one of them also reaches the same target through a real processing
    node (e.g. planning) (e.g. input->reasoning direct + input->planning->reasoning), the
    target is triggered twice (LangGraph's fan-in only joins parallel branches that finish
    in the same superstep; when supersteps are misaligned each one fires separately).
    Things like task are always read straight from state, so the direct edge is
    unnecessary as an ordering constraint — remove it.

    But "the same target has another source" alone is not enough to remove it: if that other
    source is a downstream feedback loop (e.g. review->reasoning refine), the edge from
    io.input is the only path that wakes the target. So the direct edge is removed only when
    the target is still reachable from io.input in the graph without it."""

    def _reachable(src: str, dst: str, skip: dict) -> bool:
        adjacency: dict[str, list[str]] = {}
        for e in edges:
            if e is skip:
                continue
            adjacency.setdefault(e["source"], []).append(e["target"])
        seen: set[str] = set()
        stack = [src]
        while stack:
            cur = stack.pop()
            if cur == dst:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adjacency.get(cur, []))
        return False

    nodes_by_id = {n["id"]: n for n in nodes}
    return [
        e
        for e in edges
        if not (
            nodes_by_id.get(e["source"], {}).get("type") == "io.input"
            and _reachable(e["source"], e["target"], skip=e)
        )
    ]


def _resolved_role(edge: dict) -> str:
    """The final role string of an edge. For new edges drawn on the freeform canvas,
    sourceHandle is a meaningless internal id and only the sourceRole filled in by the
    Inspector is the real role. Previously saved architectures have no sourceRole and
    their sourceHandle is already the role name (e.g. "accept"), so it is used as-is —
    this fallback makes migration free (design §1)."""
    return edge.get("sourceRole") or edge["sourceHandle"]


def _handle_targets(outgoing: dict[str, list[dict]], node_id: str) -> dict[str, str]:
    """Indexes a node's outgoing edges as resolved role -> target."""
    return {_resolved_role(e): e["target"] for e in outgoing.get(node_id, [])}


def _validate_branch_roles(node_id: str, manifest: dict, outs: list[dict]) -> None:
    """For each outgoing edge of a branching runtime node (review.intent/loop.guard/
    human.checkpoint), checks that the resolved role (_resolved_role) is one of the output
    roles the manifest declares, and that the same role is not assigned twice (design §5).

    - Unknown/unassigned role: a freeform edge was drawn but no role has been picked in the
      Inspector yet. Catches at compile time the cases where _handle_targets would silently
      ignore it (loop.guard) or the runtime would die with ValueError (review).
    - Duplicate assignment: _handle_targets is a dict, so a later edge silently overwrites an
      earlier one — generalizes the old check that only guarded loop.guard's loopBack/exit
      ports to every branching runtime node, including review/checkpoint.
    """
    valid_roles = {p["id"] for p in manifest["outputs"]}
    role_counts: dict[str, int] = {}
    for e in outs:
        role = _resolved_role(e)
        if role not in valid_roles:
            raise ValueError(
                f"node {node_id!r} has an outgoing edge with an unassigned or unknown "
                f"role {role!r} — assign one of {sorted(valid_roles)} in Inspector"
            )
        role_counts[role] = role_counts.get(role, 0) + 1
    for role, count in role_counts.items():
        if count > 1:
            raise ValueError(
                f"node {node_id!r} has {count} edges assigned the {role!r} role — "
                "each role must have exactly one outgoing edge"
            )


def _branch_labels(node_id: str, edges: list[dict]) -> list[str]:
    """Decides whether this node is a branch node by graph structure, not by type (design §5).

    If it has two or more outgoing edges carrying a label (sourceRole), it is a branch
    node and those labels are the choices the LLM picks from. A fan-out without labels is
    parallel execution, not a branch.

    Only sourceRole is considered — falling back to sourceHandle (as _resolved_role does)
    would misread every ordinary fan-out edge of an architecture saved by the old canvas
    (no sourceRole, port id stored as-is in sourceHandle) as a branch."""
    labels = [e.get("sourceRole") or "" for e in edges if e["source"] == node_id]
    labelled = [label for label in labels if label]
    return labelled if len(labelled) >= 2 else []


def _make_router(node_id: str, labels: list[str]):
    """Reads the __route__<id> value the branch node wrote to state and returns the label.
    A missing or unknown label falls back to the first label — structured output enforces
    the Literal, so the normal path never reaches this."""

    def route(state: AgentState) -> str:
        value = read_state_value(state, f"__route__{node_id}")
        return value if value in labels else labels[0]

    return route


def _tarjan_scc(node_ids: list[str], edges: list[dict]) -> list[list[str]]:
    """Tarjan SCC. A component of size >= 2 means there is at least one cycle inside it.

    Ported from findStronglyConnectedComponents in ui/src/canvas/loops/loopCandidates.ts —
    countSimpleCyclesCapped, used there for tier detection, is not ported because its UI
    display purpose is gone (design §4).
    """
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for e in edges:
        if e["source"] in adjacency:
            adjacency[e["source"]].append(e["target"])

    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []

    def strong_connect(v: str) -> None:
        nonlocal index_counter
        indices[v] = index_counter
        lowlink[v] = index_counter
        index_counter += 1
        stack.append(v)
        on_stack.add(v)

        for w in adjacency.get(v, []):
            if w not in indices:
                strong_connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node_id in node_ids:
        if node_id not in indices:
            strong_connect(node_id)

    return components


def _validate_gated_cycles(node_ids: list[str], edges: list[dict], loop_node_ids: set[str]) -> None:
    """A cycle drawn without a guard is a compile error — nothing would stop an infinite loop.

    Guard nodes' outgoing edges must be removed first: Tarjan SCC merges all cycles that
    share a node into one component, so without pruning the guard nodes, a guarded cycle
    and an unguarded cycle sharing a single node would be wholly misjudged as "guarded".
    Size-1 components (including self-loops) are out of scope.
    """
    pruned_edges = [e for e in edges if e["source"] not in loop_node_ids]
    for component in _tarjan_scc(node_ids, pruned_edges):
        if len(component) >= 2:
            raise ValueError(
                f"Cycle without a loop.guard node: {sorted(component)} — "
                "add a Loop node on the feedback edge"
            )


_PRESEEDED_STATE_KEYS = {"task", "task_tags", "intent", "criteria", "batch_mode"}


def _validate_required_inputs(nodes: list[dict]) -> None:
    """For every input an llm_step runtime node declares as required, checks that some node in
    the graph writes that state key (Tier 1 — may-analysis, no cycle/back-edge distinction,
    design §6).

    Only llm_step nodes are checked because run_llm_step is the only runtime that reads
    manifest["inputs"] directly via state.get(key). review/checkpoint/loop_guard either read
    keys fixed in their own code (make_review) or do not read manifest inputs at all, so
    checking their required flags would treat state keys that do not actually exist (e.g.
    io.output's "result") as mandatory and block valid graphs with false positives.

    Keys that initial_state() always fills (_PRESEEDED_STATE_KEYS) are treated as always
    satisfied even if there is no io.input node on the canvas.
    """
    write_keys: set[str] = set()
    for node in nodes:
        manifest = MANIFESTS_BY_TYPE.get(node["type"])
        if manifest and manifest.get("runtime") == "llm_step":
            write_keys.update(_output_write_keys(node, manifest))

    for node in nodes:
        manifest = MANIFESTS_BY_TYPE.get(node["type"])
        if not manifest or manifest.get("runtime") != "llm_step":
            continue
        for port in manifest["inputs"]:
            if not port.get("required"):
                continue
            key = port["id"]
            if key in _PRESEEDED_STATE_KEYS or key in write_keys:
                continue
            raise ValueError(
                f"node {node['id']!r} requires input {key!r} but no node in this "
                "architecture writes it, and it is not provided by the run's initial input"
            )


def _derive_loop_members(
    loop_node_id: str, continue_target: str | None, outgoing: dict[str, list[dict]]
) -> set[str]:
    """The set of nodes that start at the loopBack target and return to that loop.guard node
    = the loop body.

    Replaces the user-declared memberNodeIds of the 8/6 sidecar design by deriving it
    from graph reachability (design §3d). Decides which nodes the token/cost budget is
    attributed to.
    """
    if continue_target is None:
        return set()

    # Forward: nodes reachable from continue_target (the guard is the boundary, not crossed)
    forward: set[str] = set()
    stack = [continue_target]
    while stack:
        current = stack.pop()
        if current == loop_node_id or current in forward:
            continue
        forward.add(current)
        stack.extend(e["target"] for e in outgoing.get(current, []))

    # Backward: nodes that can return to the guard
    reverse: dict[str, list[str]] = {}
    for source, edge_list in outgoing.items():
        for e in edge_list:
            reverse.setdefault(e["target"], []).append(source)

    backward: set[str] = set()
    stack = [loop_node_id]
    while stack:
        current = stack.pop()
        if current in backward:
            continue
        backward.add(current)
        stack.extend(reverse.get(current, []))

    return forward & backward


_SCALAR_GUARD_KEYS = ("maxIterations", "maxTokens", "maxCostUsd", "maxDurationSec")


def _loop_policy_from_config(node: dict) -> dict:
    """Reassembles a loop.guard node's flat config into the nested dict evaluate_loop_guard expects.

    Thanks to this adapter, nodes/loop_guard.py (the pure guard-evaluation core) is reused
    as-is without knowing anything about the canvas node contract. If stuckThreshold is
    empty the key is omitted entirely — putting None in would make _is_stuck's
    float(None) raise TypeError.
    """
    cfg = node.get("config") or {}
    guard: dict = {key: cfg[key] for key in _SCALAR_GUARD_KEYS if cfg.get(key) is not None}
    if cfg.get("stuckWindow") is not None:
        stuck: dict = {"window": cfg["stuckWindow"]}
        if cfg.get("stuckThreshold") is not None:
            stuck["threshold"] = cfg["stuckThreshold"]
        guard["stuck"] = stuck
    return {"id": node["id"], "onExhaustion": cfg.get("onExhaustion", "exit"), "guard": guard}


def _make_loop_guard_node(
    policy: dict,
    guard_node_id: str,
    continue_target: str,
    exit_target: str | None,
    emit: EventEmitter,
    run_id: str,
):
    policy_id = policy["id"]
    on_exhaustion = policy["onExhaustion"]
    max_iterations = (policy.get("guard") or {}).get("maxIterations")

    async def loop_guard(state: AgentState) -> Command:
        await emit(make_event(run_id, guard_node_id, "node_start"))

        prior = (state.get("loop_runtime") or {}).get(policy_id)
        runtime = next_runtime(prior)
        result = evaluate_loop_guard(policy, runtime)
        update = {"iteration": runtime["iteration"], "started_at": runtime["started_at"]}

        loop_runtime_event: dict = {
            "loopNodeId": policy_id,
            "iteration": runtime["iteration"],
            "tokens": runtime["total_tokens"],
            "costUsd": runtime["total_cost_usd"],
            "durationMs": int((time.time() - runtime["started_at"]) * 1000),
        }
        if max_iterations is not None:
            loop_runtime_event["maxIterations"] = max_iterations
        if runtime["last_feedback"] is not None:
            loop_runtime_event["lastFeedback"] = runtime["last_feedback"]
        if not result["should_continue"]:
            loop_runtime_event["exitReason"] = result["exit_reason"]
        await emit(make_event(run_id, guard_node_id, "node_end", loop_runtime=loop_runtime_event))

        if result["should_continue"]:
            return Command(goto=continue_target, update={"loop_runtime": {policy_id: update}})

        if on_exhaustion == "fail":
            raise RuntimeError(
                f"loop.guard node {policy_id!r} exhausted ({result['exit_reason']}) "
                "with onExhaustion='fail'"
            )
        return Command(goto=exit_target, update={"loop_runtime": {policy_id: update}})

    return loop_guard


_CONDITIONAL_ROUTING_TYPES = {"human.checkpoint", "loop.guard"}


def _build_plain_edge_plan(
    nodes: list[dict], edges: list[dict], branch_node_ids: set[str] | None = None
) -> list[tuple[list[str], str]]:
    """Plans the regular (non-branch) edges as a list of (sources, target) pairs. With two or
    more sources they are kept together in the list, and when the caller passes them to
    graph.add_edge(sources, target) it becomes a LangGraph join-edge (waits until every source
    finishes). With one source it is a single-element [source] list — the caller registers
    it individually via graph.add_edge(source, target) (design §4).

    Edges whose source is human.checkpoint/loop.guard are excluded entirely here — these two
    route themselves via add_conditional_edges/Command(goto=...) and never call a regular
    add_edge, so edges from them cannot take part in a LangGraph join-edge in the first
    place. If a target has even one such source, no joinMode declaration is required
    (always treated as OR), and the remaining plain sources into that target are also
    handled by individual add_edge calls.

    branch_node_ids (user-defined branch nodes decided by graph structure, design §5) are
    excluded likewise — compile_graph wires them separately with add_conditional_edges, so
    including them in plain edges here would wire them twice.
    """
    branch_node_ids = branch_node_ids or set()
    nodes_by_id = {n["id"]: n for n in nodes}
    plain_sources_by_target: dict[str, list[str]] = {}
    has_conditional_source: dict[str, bool] = {}

    for e in edges:
        target = e["target"]
        source_type = nodes_by_id.get(e["source"], {}).get("type")
        if source_type in _CONDITIONAL_ROUTING_TYPES or e["source"] in branch_node_ids:
            has_conditional_source[target] = True
            continue
        sources = plain_sources_by_target.setdefault(target, [])
        if e["source"] not in sources:
            sources.append(e["source"])

    plan: list[tuple[list[str], str]] = []
    for target, sources in plain_sources_by_target.items():
        if len(sources) >= 2 and not has_conditional_source.get(target, False):
            join_mode = nodes_by_id.get(target, {}).get("joinMode")
            if join_mode not in ("and", "or"):
                raise ValueError(
                    f"node {target!r} has {len(sources)} incoming plain edges and no "
                    "joinMode — add join: all or join: any to the node in arch.yaml"
                )
            if join_mode == "and":
                plan.append((sources, target))
                continue
        for source in sources:
            plan.append(([source], target))
    return plan


def compile_graph(architecture: dict, default_model_cfg: dict, emit: EventEmitter, run_id: str):
    nodes: list[dict] = architecture.get("nodes") or []
    raw_edges: list[dict] = architecture.get("edges") or []

    if not nodes:
        raise ValueError("Architecture has no nodes")
    _validate_required_inputs(nodes)

    edges = _filter_control_edges(nodes, raw_edges)

    outgoing: dict[str, list[dict]] = {}
    incoming: dict[str, list[dict]] = {}
    for e in edges:
        outgoing.setdefault(e["source"], []).append(e)
        incoming.setdefault(e["target"], []).append(e)

    loop_node_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}
    _validate_gated_cycles([n["id"] for n in nodes], edges, loop_node_ids)

    # Derive the loop body to attribute the token/cost budget to from the graph (design §3d).
    # The parameter name loop_policy_ids is kept so review/llm_step need no changes.
    node_to_policies: dict[str, list[str]] = {}
    for loop_node_id in sorted(loop_node_ids):
        continue_target = _handle_targets(outgoing, loop_node_id).get("loopBack")
        for member_id in sorted(_derive_loop_members(loop_node_id, continue_target, outgoing)):
            node_to_policies.setdefault(member_id, []).append(loop_node_id)

    # Decide branch nodes by graph structure (design §5) — review.intent/human.checkpoint/
    # loop.guard are excluded because their runtime decides the labels, and keep the existing
    # path. Only llm_step runtimes are considered because a branch is defined as "the LLM picks
    # one of them"; if io.input/io.output/model.binding/loop.reentry (passthrough), which have
    # no structured output, happened to carry 2 labels (e.g. descriptive labels added for
    # human readability), they must not be mistaken for branches and intercepted with
    # add_conditional_edges — nobody writes route, so it would always fall to the first label
    # and the other fan-out would silently never run.
    branch_node_ids = {
        n["id"]
        for n in nodes
        if n["type"] not in _CONDITIONAL_ROUTING_TYPES
        and MANIFESTS_BY_TYPE.get(n["type"], {}).get("runtime") == "llm_step"
        and _branch_labels(n["id"], edges)
    }

    graph = StateGraph(AgentState)

    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        manifest = MANIFESTS_BY_TYPE.get(node_type)
        if manifest is None:
            raise ValueError(f"Unknown node type: {node_type!r} (node {node_id!r})")

        if node_type in PASSTHROUGH_TYPES:
            graph.add_node(
                node_id,
                _make_passthrough_node(node_id, node_type, node.get("config") or {}, emit, run_id),
            )
        elif manifest.get("runtime") == "llm_step":
            model, policy = _resolve_model(node, default_model_cfg)
            graph.add_node(
                node_id,
                _make_llm_step_node(
                    node,
                    manifest,
                    model,
                    policy,
                    emit,
                    run_id,
                    node_to_policies.get(node_id),
                    branch_labels=(
                        _branch_labels(node_id, edges) if node_id in branch_node_ids else None
                    ),
                ),
            )
        elif manifest.get("runtime") == "checkpoint":
            _validate_branch_roles(node_id, manifest, outgoing.get(node_id, []))
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update(_handle_targets(outgoing, node_id))
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
        elif manifest.get("runtime") == "loop_guard":
            loop_policy = _loop_policy_from_config(node)
            _validate_branch_roles(node_id, manifest, outgoing.get(node_id, []))
            targets = _handle_targets(outgoing, node_id)
            continue_target = targets.get("loopBack")
            exit_target = targets.get("exit")
            on_exhaustion = loop_policy["onExhaustion"]

            if continue_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} has no 'loopBack' edge — "
                    "wire the Loop back port to the node the loop re-enters"
                )
            if on_exhaustion not in ("exit", "escalate", "fail"):
                raise ValueError(
                    f"loop.guard node {node_id!r} has invalid onExhaustion "
                    f"{on_exhaustion!r} (must be 'exit', 'escalate', or 'fail')"
                )
            if on_exhaustion in ("exit", "escalate") and exit_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} onExhaustion={on_exhaustion!r} "
                    "requires a wired 'exit' port"
                )

            graph.add_node(
                node_id,
                _make_loop_guard_node(
                    loop_policy,
                    node_id,
                    continue_target=continue_target,
                    exit_target=exit_target,
                    emit=emit,
                    run_id=run_id,
                ),
            )
        else:
            raise ValueError(f"Unsupported node type in compiler: {node_type!r}")

    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        manifest = MANIFESTS_BY_TYPE.get(node_type, {})

        # checkpoint/loop_guard runtimes route themselves via Command(goto=...), so
        # no plain edge is added.
        if manifest.get("runtime") in ("checkpoint", "loop_guard"):
            continue
        if node_id in branch_node_ids:
            # A user node decided to be a branch by graph structure (design §5) — uses a separate
            # router that reads the __route__<id> state key instead of route_fns.
            labels = _branch_labels(node_id, edges)
            # If any outgoing edge without a label is mixed in, that edge is caught neither by the
            # targets dict below (no sourceRole) nor by _build_plain_edge_plan (the source is in
            # branch_node_ids so it is excluded wholesale), and silently disappears (BLOCKING 1) —
            # same rule as _validate_branch_capable in archfile.py; here it guards the raw
            # architecture dict path (dispatch_graph) that arrives without going through parse_arch.
            unlabelled = [e for e in outgoing.get(node_id, []) if not e.get("sourceRole")]
            if unlabelled:
                raise ValueError(
                    f"node {node_id!r} branches ({len(labels)} labelled outgoing edges) "
                    f"but also has {len(unlabelled)} unlabelled outgoing edge(s) to "
                    f"{[e['target'] for e in unlabelled]} — assign a role in Inspector "
                    "or it will silently never run"
                )
            # Duplicate label check — role duplicates for review.intent/human.checkpoint/loop.guard
            # are already blocked by _validate_branch_roles (above); this structural branch path
            # generalizes that, and without the same defense a duplicate label would be silently
            # collapsed into one in the dict comprehension, leaving the remaining edges
            # unreachable. _validate_branch_capable in archfile.py checks the same rule in the
            # parser (with line numbers), but dispatch_graph in main.py passes the architecture
            # dict saved from the canvas straight to compile_graph without parse_arch, so without
            # this check that path is unguarded — neither is a redundant duplicate to remove.
            label_counts: dict[str, int] = {}
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
            for label, count in label_counts.items():
                if count > 1:
                    raise ValueError(
                        f"node {node_id!r} has {count} edges assigned the {label!r} "
                        "label — each label must have exactly one outgoing edge"
                    )
            targets = {
                (e.get("sourceRole") or ""): e["target"]
                for e in edges
                if e["source"] == node_id and e.get("sourceRole")
            }
            graph.add_conditional_edges(node_id, _make_router(node_id, labels), targets)
            continue
        if not outgoing.get(node_id):
            graph.add_edge(node_id, END)

    for sources, target in _build_plain_edge_plan(nodes, edges, branch_node_ids):
        if len(sources) > 1:
            graph.add_edge(sources, target)
        else:
            graph.add_edge(sources[0], target)

    entry_ids = [n["id"] for n in nodes if not incoming.get(n["id"])]
    if not entry_ids:
        raise ValueError("Architecture has no entry node (a node with no incoming edges)")
    for eid in entry_ids:
        graph.add_edge(START, eid)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
