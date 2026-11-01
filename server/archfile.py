"""arch.yaml → Architecture dict.

flow: block is plain mermaid flowchart syntax — we do not invent our own grammar.
So the same string can be passed straight to browser mermaid to draw the diagram,
and the parser needs just one regex (design §3.2).
"""

import re
from pathlib import PurePosixPath
from typing import TypedDict

import yaml


class ArchError(ValueError):
    """Reason an arch.yaml was rejected. If line is set, the user is shown the line number."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


class FlowEdge(TypedDict):
    source: str
    target: str
    label: str
    line: int


# Scans "a -->|label| b --> c". Labels are mostly arbitrary strings — the only exceptions
# are loop.guard (loopBack/exit) and human.checkpoint (approve/revise/reject), which
# users cannot create (design §3.1-3).
_HOP = re.compile(r"\s*-->\s*(?:\|(.*?)\|\s*)?")
_NAME = re.compile(r"[^\s|>-](?:(?!-->)[^\s|])*")

# Directive on the first line of a mermaid document, such as `flowchart LR`/`graph TD`. Pasting
# the `flow:` block as-is into GitHub/Obsidian to render it as mermaid requires this header,
# but to our parser it is a line with no arrow, so it used to be rejected as "expected '-->'" —
# it is now skipped, for the first line only (design §3.2).
_DIRECTIVE = re.compile(r"^(flowchart|graph)\b")


def parse_flow(text: str, line_offset: int = 0) -> list[FlowEdge]:
    """Scan text (flow: contents extracted as a YAML block scalar) and build edges.

    line_offset says which line of the original document text's first line actually is
    (default 0 — for direct parse_flow calls/tests where text is already the whole file).
    parse_arch precomputes this via _flow_line_offset and passes it in — so any ArchError
    thrown inside carries a file-relative line number just like the edges on the success path
    (BLOCKING 2: previously the offset was added after the fact only to successful edges, so
    on the failure path block-relative line numbers leaked out)."""
    edges: list[FlowEdge] = []
    seen_content = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if not seen_content:
            seen_content = True
            if _DIRECTIVE.match(line):
                continue
        edges.extend(_parse_flow_line(line, lineno + line_offset))
    return edges


def _parse_flow_line(line: str, lineno: int) -> list[FlowEdge]:
    names: list[str] = []
    labels: list[str] = []
    pos = 0
    while pos < len(line):
        name = _NAME.match(line, pos)
        if not name:
            raise ArchError(f"cannot read node name in {line!r}", lineno)
        names.append(name.group(0))
        pos = name.end()
        if pos >= len(line):
            break
        hop = _HOP.match(line, pos)
        if not hop:
            raise ArchError(f"expected '-->' in {line!r}", lineno)
        labels.append(hop.group(1) or "")
        pos = hop.end()
        if pos >= len(line):
            raise ArchError(f"trailing arrow with no target in {line!r}", lineno)
    if len(names) < 2:
        raise ArchError(f"not an edge: {line!r}", lineno)
    return [
        FlowEdge(source=names[i], target=names[i + 1], label=labels[i], line=lineno)
        for i in range(len(names) - 1)
    ]


# Nodes users cannot create with a prompt — only boundaries and runtime devices (design §2).
PREDEFINED = {
    "input": "io.input",
    "output": "io.output",
    "human.checkpoint": "human.checkpoint",
    "loop.guard": "loop.guard",
}

# Type emitted for user-defined nodes. The manifest is an empty llm_step node, so compile_graph
# reads config.inputs/outputs/systemPrompt as-is (design §4).
USER_NODE_TYPE = "custom.node"
# `run: agent` — same in/out/prompt/model as a user node, run by mini-swe-agent (nodes/agent_step).
AGENT_NODE_TYPE = "agent.node"
_AGENT_LIMITS = {"steps", "cost", "memory_mb", "cpu_seconds"}

# Types that compile.py `_branch_labels` (design §5) accepts as branches — only types that
# have a way to pick a label themselves (LLM structured output or runtime-specific logic)
# can be branch nodes. io.input/io.output are not here — they have no way to emit a label,
# so attaching 2+ labels would silently discard user intent (same class as the Task 3 diamond bug).
_BRANCH_CAPABLE_TYPES = {USER_NODE_TYPE, "human.checkpoint", "loop.guard"}


def _split_model(spec: str) -> tuple[str, str]:
    """'google/gemini-3.1-flash-lite' → ('google', 'gemini-3.1-flash-lite')."""
    provider, _, model = spec.partition("/")
    if not model:
        raise ArchError(f"model must be 'provider/model', got {spec!r}")
    return provider, model


def _ports(names: list[str]) -> list[dict]:
    return [{"id": n, "label": n} for n in names]


_FLOW_KEY = re.compile(r"^flow\s*:\s*(.*)$")


def _flow_line_offset(text: str) -> int:
    """Which line of the original document the first line of the flow: block is (pass it
    straight to parse_flow's line_offset argument).

    A block scalar (`flow: |`) starts its content on the line after flow:, so the offset is
    the flow: line number itself (content line 1 + offset = flow: line + 1). An inline scalar
    (`flow: "a --> b"`) has its content on the same physical line as flow:, so the offset
    must be one less (content line 1 + offset = flow: line) — without this distinction
    inline scalar line numbers would be off by one."""
    for i, line in enumerate(text.splitlines(), start=1):
        m = _FLOW_KEY.match(line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest and rest[0] not in "|>":
            return i - 1  # inline scalar — content is on this line
        return i  # block scalar (| or >) — content starts on the next line
    return 0


def parse_arch(text: str, default_model: str | None = None) -> tuple[dict, list[str]]:
    """arch.yaml text → (Architecture dict, list of warnings).

    default_model, if given, replaces the top-level model: (a node's own model: still wins)."""
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        # problem_mark is a 0-based line number relative to the whole document — unlike
        # parse_flow's result,
        # _flow_line_offset must not be added (it is already file-relative, so that would
        # double-correct).
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise ArchError(str(e), line) from e
    flow_text = doc.get("flow") or ""
    raw_nodes = doc.get("nodes") or {}
    default_model = default_model or doc.get("model")

    flow_edges = parse_flow(flow_text, _flow_line_offset(text))
    # Node list order = order of first appearance in flow. dict.fromkeys preserves insertion order,
    # so use it rather than a set comprehension (hash order — random per process). Task 3's
    # back-edge
    # (loop) detection uses this order as a topological approximation, so it must be deterministic.
    referenced = dict.fromkeys(n for e in flow_edges for n in (e["source"], e["target"]))

    nodes: list[dict] = []
    produced: dict[str, str] = {}  # out name → id of the node that produces it
    warnings: list[str] = []

    for name in referenced:
        spec = raw_nodes.get(name)
        if spec is None and name not in PREDEFINED:
            line = next(e["line"] for e in flow_edges if name in (e["source"], e["target"]))
            raise ArchError(f"node {name!r} is used in flow but not defined in nodes:", line)
        nodes.append(_build_node(name, spec or {}, default_model, produced, warnings))

    for name in raw_nodes:
        if name not in referenced:
            warnings.append(f"node {name!r} is defined but never used in flow:")

    _validate_inputs(raw_nodes)
    _validate_branch_capable(nodes, flow_edges)
    _validate_fan_in(nodes, flow_edges, raw_nodes)

    edges = [
        {
            "id": f"e{i}",
            "source": e["source"],
            "target": e["target"],
            "sourceHandle": e["label"] or "out",
            "sourceRole": e["label"],
            "targetHandle": "in",
        }
        for i, e in enumerate(flow_edges)
    ]
    nodes, edges = _insert_guards(nodes, edges)
    return {
        "version": "0.1",
        "metadata": {"name": doc.get("name") or "untitled"},
        "nodes": nodes,
        "edges": edges,
        "flow": flow_text,  # original string for frontend mermaid rendering
    }, warnings


def _build_node(
    name: str, spec: dict, default_model: str | None, produced: dict, warnings: list
) -> dict:
    run = spec.get("run")
    if (run is not None and run != "agent") or name in PREDEFINED:
        type_ = PREDEFINED.get(run or name)
        if type_ is None:
            raise ArchError(f"unknown run: {run!r} — expected agent or one of {sorted(PREDEFINED)}")
        config = {k: v for k, v in spec.items() if k != "run"}
        if "max" in config:
            config["maxIterations"] = config.pop("max")
        node = {"id": name, "type": type_, "position": {"x": 0, "y": 0}, "config": config}
        if "join" in config:
            node["joinMode"] = _join_mode(name, config.pop("join"))
        return node

    outs = spec.get("out") or []
    for out in outs:
        if out in produced:
            warnings.append(
                f"nodes {produced[out]!r} and {name!r} both write {out!r} — "
                "the later one wins; rename if that is not intended"
            )
        produced[out] = name

    model_spec = spec.get("model") or default_model
    if not model_spec and ("temperature" in spec or "max_tokens" in spec):
        raise ArchError(
            f"node {name!r} sets temperature/max_tokens but has no model — "
            "add model: to the node or the file"
        )
    temp = spec.get("temperature", 0)
    if isinstance(temp, bool) or not isinstance(temp, int | float):
        raise ArchError(f"node {name!r}: temperature must be a number, got {temp!r}")
    mt = spec.get("max_tokens")
    if "max_tokens" in spec and (isinstance(mt, bool) or not isinstance(mt, int) or mt <= 0):
        raise ArchError(f"node {name!r}: max_tokens must be a positive integer, got {mt!r}")
    slots = []
    if model_spec:
        provider, model = _split_model(model_spec)
        slots = [
            {
                "id": f"slot-{name}",
                "provider": provider,
                "model": model,
                "temperature": temp,
                "role": "",
            }
        ]
        if "max_tokens" in spec:
            slots[0]["maxTokens"] = spec["max_tokens"]
    node = {
        "id": name,
        "type": USER_NODE_TYPE,
        "position": {"x": 0, "y": 0},
        "config": {
            "label": name,
            "systemPrompt": spec.get("prompt") or "",
            "inputs": _ports(spec.get("in") or []),
            "outputs": _ports(outs),
            "modelSlots": slots,
        },
    }
    if "join" in spec:
        node["joinMode"] = _join_mode(name, spec["join"])
    if run == "agent":
        node["type"] = AGENT_NODE_TYPE
        node["config"].update(_agent_config(name, spec))
    return node


def _agent_config(name: str, spec: dict) -> dict:
    if len(spec.get("out") or []) != 1:
        raise ArchError(f"agent node {name!r} needs exactly one out: (its final answer)")
    limits = spec.get("limits") or {}
    if not isinstance(limits, dict) or set(limits) - _AGENT_LIMITS:
        raise ArchError(f"agent node {name!r}: limits takes only {sorted(_AGENT_LIMITS)}")
    for k, v in limits.items():
        if k in ("memory_mb", "cpu_seconds"):
            if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                raise ArchError(f"agent node {name!r}: limits.{k} must be a positive integer")
        elif isinstance(v, bool) or not isinstance(v, int | float) or v <= 0:
            raise ArchError(f"agent node {name!r}: limits.{k} must be a positive number")
    network = spec.get("network", False)
    if not isinstance(network, bool):
        raise ArchError(f"agent node {name!r}: network must be true or false")
    secrets = spec.get("secrets") or []
    if not isinstance(secrets, list) or not all(isinstance(s, str) for s in secrets):
        raise ArchError(f"agent node {name!r}: secrets must be a list of env var names")
    cfg = {"limits": limits, "network": network, "secrets": secrets}
    if "tools" in spec:
        tools = spec["tools"]
        if not isinstance(tools, list) or not all(
            isinstance(t, str) and re.fullmatch(r"[A-Za-z0-9._+-]+", t) for t in tools
        ):
            raise ArchError(f"agent node {name!r}: tools must be a list of command names")
        cfg["tools"] = tools
    if "files" in spec:
        cfg["files"] = _files_scope(name, spec["files"])
    return cfg


def _files_scope(name: str, raw: object) -> dict[str, list[str]]:
    who = f"agent node {name!r}"
    if not isinstance(raw, dict):
        raise ArchError(f"{who}: files must be a mapping with read/write lists")
    if set(raw) - {"read", "write"}:
        raise ArchError(f"{who}: files takes only ['read', 'write']")
    scope: dict[str, list[str]] = {}
    for key in ("read", "write"):
        paths = raw.get(key) or []
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise ArchError(f"{who}: files.{key} must be a list of folders")
        scope[key] = []
        for p in paths:
            pp = PurePosixPath(p)
            if pp.is_absolute() or ".." in pp.parts or ".git" in pp.parts:
                raise ArchError(
                    f"{who}: files.{key}: {p!r} must be a relative folder inside files/ "
                    "(no '..' or '.git')"
                )
            scope[key].append(pp.as_posix())
    for p in scope["read"]:
        if p in scope["write"]:
            raise ArchError(f"{who}: {p!r} is in both files.read and files.write")
    return scope


def _join_mode(name: str, value: object) -> str:
    if value not in ("all", "any"):
        raise ArchError(f"node {name!r}: join must be 'all' or 'any', got {value!r}")
    return "and" if value == "all" else "or"


# Same meaning as compile.py's _PRESEEDED_STATE_KEYS — values already in state when the run starts.
_PRESEEDED = {"task", "task_tags", "intent", "criteria", "batch_mode"}


def _validate_inputs(raw_nodes: dict) -> None:
    """For every name that in: requires, check that some out: anywhere in nodes: produces it.
    It looks at the whole graph, not flow order, so a later-running node that feeds back
    through a loop (design §5.1) also passes — only genuine typos are caught."""
    produced_all = {
        out
        for spec in raw_nodes.values()
        if isinstance(spec, dict)
        for out in spec.get("out") or []
    }
    for name, spec in raw_nodes.items():
        if not isinstance(spec, dict):
            continue
        for want in spec.get("in") or []:
            if want not in produced_all and want not in _PRESEEDED:
                raise ArchError(
                    f"node {name!r} reads {want!r} but no node writes it — "
                    "add it to some node's out:"
                )


def _validate_branch_capable(nodes: list[dict], flow_edges: list[FlowEdge]) -> None:
    """Same rule as compile.py `_branch_labels` (design §5) — a node with two or more labelled
    outgoing edges is a branch node — applied first in the parser: if two or more labels are
    attached to a type that cannot branch (io.input/io.output), reject with a line number.
    Duplicate labels on the same node are also blocked here — both are the same class of trap,
    "does not run as written, with no signal".

    Only looks at flow_edges (the edges the user actually wrote in mermaid) — the synthetic
    loopBack/exit edges that _insert_guards adds later are not here, so auto-inserted guards
    are never subject to this, and a guard the user pulled out directly with `{ run: loop.guard }`
    is already in the branchable list because its type is loop.guard.

    The duplicate-label check also exists in compile.py's branch-wiring loop (not a duplicate) —
    an architecture dict saved from the canvas goes straight from main.py's dispatch_graph to
    compile_graph without passing through this parser, so it must be blocked there too to
    avoid silently dropping edges. The only difference is that here (the parser) gives arch.yaml
    authors a line number."""
    node_types = {n["id"]: n["type"] for n in nodes}
    labelled_by_source: dict[str, list[tuple[str, int]]] = {}
    unlabelled_by_source: dict[str, list[int]] = {}
    for e in flow_edges:
        if e["label"]:
            labelled_by_source.setdefault(e["source"], []).append((e["label"], e["line"]))
        else:
            unlabelled_by_source.setdefault(e["source"], []).append(e["line"])

    for node_id, labelled in labelled_by_source.items():
        if len(labelled) < 2:
            continue
        if node_types.get(node_id) not in _BRANCH_CAPABLE_TYPES:
            labels = [label for label, _ in labelled]
            raise ArchError(
                f"node {node_id!r} has {len(labels)} labelled outgoing edges {labels} "
                "but cannot branch — only user-defined nodes, human.checkpoint, and "
                "loop.guard can",
                labelled[0][1],
            )
        seen: dict[str, int] = {}
        for label, line in labelled:
            if label in seen:
                raise ArchError(
                    f"node {node_id!r} has the {label!r} label on two outgoing edges — "
                    "each label must have exactly one outgoing edge",
                    line,
                )
            seen[label] = line
        # If there are 2+ labels (branch confirmed) and even one more unlabelled outgoing edge,
        # that edge is caught nowhere in compile.py (neither the plain edge plan nor the branch
        # targets dict) and silently vanishes (BLOCKING 1) — reject immediately.
        if node_id in unlabelled_by_source:
            raise ArchError(
                f"node {node_id!r} branches ({len(labelled)} labelled outgoing edges) "
                "but also has an unlabelled outgoing edge — label it or it will "
                "silently never run",
                unlabelled_by_source[node_id][0],
            )


def _validate_fan_in(nodes: list[dict], flow_edges: list[FlowEdge], raw_nodes: dict) -> None:
    """A node fed by 2+ distinct plain sources needs join: all|any. Same exemptions as
    compile._build_plain_edge_plan: checkpoint/guard sources are ignored, and any labelled
    incoming edge means the target is a branch merge (no join needed)."""
    node_types = {n["id"]: n["type"] for n in nodes}
    labelled_targets = {e["target"] for e in flow_edges if e["label"]}
    # Back edges are re-routed through a guard (_insert_guards), so they are not plain fan-in.
    back = {id(e) for e in _back_edges(nodes, flow_edges)}  # type: ignore[arg-type]
    sources: dict[str, dict[str, int]] = {}  # target -> {source: line of first edge}
    lines: dict[str, list[int]] = {}
    for e in flow_edges:
        if (
            e["label"]
            or id(e) in back
            or node_types.get(e["source"]) in ("human.checkpoint", "loop.guard")
        ):
            continue
        first = sources.setdefault(e["target"], {})
        if e["source"] not in first:
            first[e["source"]] = e["line"]
            lines.setdefault(e["target"], []).append(e["line"])
    for target, by_source in sources.items():
        if len(by_source) < 2 or target in labelled_targets:
            continue
        spec = raw_nodes.get(target)
        if isinstance(spec, dict) and "join" in spec:
            continue
        raise ArchError(
            f"node {target!r} has {len(by_source)} incoming edges — add join: all "
            "(wait for every one) or join: any (run on each)",
            lines[target][1],
        )


DEFAULT_MAX_ITERATIONS = 3


def _back_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Find genuine cycles with DFS — only an edge toward a node in progress (gray, on the
    current recursion stack) is a back edge (textbook definition). Pure reachability ("v
    reaches u") must not be used: a fan-out then fan-in (diamond) alone makes non-cycle
    forward edges look backward (first-appearance order depends on the visit path), and a
    cycle with several edges (3 for a 3-cycle) would have all of them flagged as back edges,
    inserting duplicate guards — only the gray-stack test yields exactly one per cycle.

    DFS roots and each node's adjacent edges are each traversed in nodes/edges list order
    for determinism. A fresh DFS starts from every unvisited node so components not reachable
    from the first root are not missed.
    """
    adjacency: dict[str, list[dict]] = {n["id"]: [] for n in nodes}
    for e in edges:
        adjacency.setdefault(e["source"], []).append(e)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys((n["id"] for n in nodes), WHITE)
    back: list[dict] = []

    # Unroll the recursive DFS into an explicit stack — avoids RecursionError killing the whole
    # parse when a long straight chain (hundreds to thousands of nodes) exceeds Python's default
    # recursion limit (1000). A frame is [node_id, index of next adjacent edge] — colours are
    # painted
    # and edges scanned in the same order as the recursive version, so back-edge results are
    # identical.
    for start in nodes:
        start_id = start["id"]
        if color[start_id] != WHITE:
            continue
        color[start_id] = GRAY
        stack: list[list] = [[start_id, 0]]
        while stack:
            frame = stack[-1]
            node_id, i = frame
            out_edges = adjacency[node_id]
            if i < len(out_edges):
                frame[1] += 1
                e = out_edges[i]
                target_color = color.get(e["target"], WHITE)
                if target_color == GRAY:
                    back.append(e)
                elif target_color == WHITE:
                    color[e["target"]] = GRAY
                    stack.append([e["target"], 0])
            else:
                color[node_id] = BLACK
                stack.pop()

    return back


def _terminal_node_id(nodes: list[dict], edges: list[dict]) -> str:
    """The node with no outgoing edges. There must be exactly one."""
    sources = {e["source"] for e in edges}
    terminals = [n["id"] for n in nodes if n["id"] not in sources]
    if len(terminals) != 1:
        raise ArchError(
            f"cannot pick a loop exit target — found {len(terminals)} terminal nodes "
            f"{sorted(terminals)}; declare the guard explicitly with "
            "{ run: loop.guard, max: N } and wire its exit edge"
        )
    return terminals[0]


def _insert_guards(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Insert a default guard on every back edge that has none (design §5.1).

    a -->|retry| b  ⇒  a -->|retry| __guard_N,
                        __guard_N -->|loopBack| b, __guard_N -->|exit| <terminal>
    """
    guard_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}
    pending = [e for e in _back_edges(nodes, edges) if e["source"] not in guard_ids]
    if not pending:
        return nodes, edges

    terminal = _terminal_node_id(nodes, edges)
    for i, edge in enumerate(pending, start=1):
        gid = f"__guard_{i}"
        nodes.append(
            {
                "id": gid,
                "type": "loop.guard",
                "position": {"x": 0, "y": 0},
                "config": {
                    "kind": "critiqueRevise",
                    "maxIterations": DEFAULT_MAX_ITERATIONS,
                    "onExhaustion": "exit",
                    "synthetic": True,  # basis for the dashboard showing this as "default"
                },
            }
        )
        loop_target = edge["target"]
        edge["target"] = gid
        edges.append(
            {
                "id": f"{gid}-back",
                "source": gid,
                "target": loop_target,
                "sourceHandle": "loopBack",
                "sourceRole": "loopBack",
                "targetHandle": "in",
            }
        )
        edges.append(
            {
                "id": f"{gid}-exit",
                "source": gid,
                "target": terminal,
                "sourceHandle": "exit",
                "sourceRole": "exit",
                "targetHandle": "in",
            }
        )
    return nodes, edges
