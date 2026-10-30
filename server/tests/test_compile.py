"""Unit tests for graphs/compile.py — Architecture -> StateGraph. LLM is mocked (AGENTS.md §6)."""

import pytest
from langgraph.types import Command
from pydantic import ValidationError

import graphs.compile as compile_mod
from events import ListEventEmitter
from nodes.loop_guard import evaluate_loop_guard
from state import empty_loop_runtime, initial_state

DEFAULT_MODEL_CFG = {"provider": "anthropic", "model": "claude-3", "temperature": 0}

# With the 2026-09-02 text-first switch (task 7), these three (reasoning.cot/planning.decompose/
# review.intent) were dropped from BUILTIN_MANIFESTS (manifests.py) — arch.yaml now produces
# only custom.node (+io.input/io.output/human.checkpoint/loop.guard).
# But compile.py's llm_step/review runtime dispatch itself (and nodes/review.py's
# make_review — live code that treatment.py still uses directly) was not removed.
# This suite must keep verifying that general compile machinery (join edges, branch role
# validation, loop-guard axis, cycle validation, etc.), so it revives these types locally
# in MANIFESTS_BY_TYPE using the same monkeypatch.setitem pattern this file already used
# for test.custom_writer/test.needs_summary — they are not in the production catalog.
_RETIRED_TEST_MANIFESTS = [
    {
        "type": "planning.decompose",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Planning",
        "description": "Break the task down into steps.",
        "inputs": [{"id": "task", "label": "Task", "dataType": "text", "required": True}],
        "outputs": [{"id": "plan", "label": "Plan", "dataType": "plan"}],
        "config": [],
        "defaults": {
            "outputSchema": {"steps": "string[]"},
            "outputKeyMap": {"steps": "plan"},
        },
    },
    {
        "type": "reasoning.cot",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Reasoning",
        "description": "Chain-of-thought reasoning.",
        "inputs": [
            {"id": "task", "label": "Task", "dataType": "text", "required": True},
            {"id": "plan", "label": "Plan", "dataType": "plan", "required": False},
        ],
        "outputs": [
            {"id": "answer", "label": "Answer", "dataType": "text"},
            {"id": "confidence", "label": "Confidence", "dataType": "number"},
        ],
        "config": [],
        "defaults": {
            "outputSchema": {"answer": "string", "confidence": "number"},
            "extraInputs": [{"id": "feedback", "label": "Previous Feedback"}],
        },
    },
]
# review.intent (runtime "review") is not here — when review.intent was also dropped from
# _CONDITIONAL_ROUTING_TYPES (task 7), add_conditional_edges and the plain edges of
# _build_plain_edge_plan really did get wired twice on the same source (observed: infinite
# recursion). No manifest in production uses runtime "review" any more, so that path is
# unreachable; instead of reviving the regression here, tests that exercised review's
# 3-way branch execution are replaced below with human.checkpoint (structural validation)
# or deleted.


@pytest.fixture(autouse=True)
def _restore_retired_manifests(monkeypatch):
    for manifest in _RETIRED_TEST_MANIFESTS:
        monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, manifest["type"], manifest)


def _arch(nodes, edges):
    return {"version": "1", "metadata": {"name": "test"}, "nodes": nodes, "edges": edges}


def _node(id_, type_, config=None):
    return {"id": id_, "type": type_, "position": {"x": 0, "y": 0}, "config": config or {}}


def _edge(source, target, source_handle="out", target_handle="in", source_role=None):
    edge = {
        "id": f"e-{source}-{target}",
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }
    if source_role is not None:
        edge["sourceRole"] = source_role
    return edge


def test_resolved_role_prefers_source_role_over_handle():
    """A new freeform edge has a meaningless internal id as sourceHandle, so sourceRole is used."""
    edge = _edge("a", "b", source_handle="opaque-1", source_role="accept")
    assert compile_mod._resolved_role(edge) == "accept"


def test_resolved_role_falls_back_to_source_handle_when_no_role():
    """A previously saved architecture has no sourceRole; sourceHandle is already the role name."""
    edge = _edge("a", "b", source_handle="accept")
    assert compile_mod._resolved_role(edge) == "accept"


def test_handle_targets_resolves_via_source_role():
    outgoing = {
        "review": [_edge("review", "output", source_handle="opaque-1", source_role="accept")]
    }
    assert compile_mod._handle_targets(outgoing, "review") == {"accept": "output"}


def test_validate_branch_roles_raises_for_unassigned_role():
    """A freeform edge drawn but with no role picked in the Inspector yet — no sourceRole,
    and the opaque sourceHandle is not a valid role name."""
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    outs = [_edge("review", "output", source_handle="opaque-1")]
    with pytest.raises(ValueError, match="unassigned or unknown"):
        compile_mod._validate_branch_roles("review", manifest, outs)


def test_validate_branch_roles_accepts_freeform_edge_with_source_role():
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    outs = [_edge("review", "output", source_handle="opaque-1", source_role="approve")]
    compile_mod._validate_branch_roles("review", manifest, outs)  # must pass without raising


def test_validate_branch_roles_raises_for_duplicate_role():
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    outs = [
        _edge("review", "a", source_handle="revise"),
        _edge("review", "b", source_handle="opaque-2", source_role="revise"),
    ]
    with pytest.raises(ValueError, match=r"2 edges assigned the 'revise' role"):
        compile_mod._validate_branch_roles("review", manifest, outs)


def test_validate_branch_roles_accepts_distinct_roles():
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    outs = [
        _edge("review", "a", source_handle="approve"),
        _edge("review", "b", source_handle="revise"),
    ]
    compile_mod._validate_branch_roles("review", manifest, outs)  # must pass without raising


def test_validate_branch_roles_accepts_empty_outs():
    manifest = compile_mod.MANIFESTS_BY_TYPE["human.checkpoint"]
    compile_mod._validate_branch_roles("checkpoint", manifest, [])  # must pass without raising


def _gated_refine_arch(guard_config: dict, review_config: dict | None = None) -> dict:
    """A gated refine loop shaped like the starter graph.

    With review.intent retired by the 2026-09-02 text-first switch (task 7), the node that
    sends the guard its refine signal here is not review.intent but the custom.node
    'reviewer', which branches structurally (2 sourceRole labels + the LLM-chosen __route__)
    — the review_config argument is still accepted for signature compatibility with old
    callers but is no longer used (ignored).

    input → reasoning → reviewer
    reviewer --refine--> guard --loopBack--> reasoning
    reviewer --accept--> output      guard --exit--> output
    """
    return _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("reviewer", "custom.node", {"outputs": [{"id": "verdict", "label": "Verdict"}]}),
            _node("guard", "loop.guard", {"onExhaustion": "exit", **guard_config}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "reviewer", "answer"),
            _edge("reviewer", "guard", "refine", "in", source_role="refine"),
            _edge("reviewer", "output", "accept", "result", source_role="accept"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
        ],
    )


_ONE_CRITERION = [{"id": "c1", "text": "Includes the correct answer", "severity": "must_pass"}]


async def fake_llm_step(state, *, node_id, **kwargs):
    if node_id == "planning":
        return {"steps": ["s1"]}
    if node_id == "reasoning":
        return {"answer": "4", "confidence": 0.9}
    if node_id == "reviewer":
        # The structural branch node of _gated_refine_arch — the guard-trip tests in this file
        # are all "review rejects to the very end" scenarios, so it always sends back to refine.
        return {"verdict": "unmet", "route": "refine"}
    return {}


def _patch_model(monkeypatch):
    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)


def test_build_output_model_creates_pydantic_model_matching_output_schema():
    model = compile_mod._build_output_model("planning.decompose", {"steps": "string[]"})
    instance = model(steps=["s1", "s2"])
    assert instance.model_dump() == {"steps": ["s1", "s2"]}


def test_build_output_model_supports_scalar_types():
    model = compile_mod._build_output_model(
        "reasoning.cot", {"answer": "string", "confidence": "number"}
    )
    instance = model(answer="4", confidence=0.9)
    assert instance.model_dump() == {"answer": "4", "confidence": 0.9}


def test_output_write_keys_applies_output_key_map():
    manifest = {
        "defaults": {
            "outputSchema": {"steps": "string[]"},
            "outputKeyMap": {"steps": "plan"},
        }
    }
    assert compile_mod._output_write_keys(_node("n1", "planning.decompose"), manifest) == ["plan"]


def test_output_write_keys_defaults_to_identity_without_key_map():
    manifest = {"defaults": {"outputSchema": {"answer": "string", "confidence": "number"}}}
    assert compile_mod._output_write_keys(_node("n1", "reasoning.cot"), manifest) == [
        "answer",
        "confidence",
    ]


def test_output_write_keys_derives_from_instance_config_when_manifest_has_no_output_schema():
    """Phase B④: custom.node has no outputSchema in its manifest — it is derived on the fly
    from this node instance's config.outputs ports (all treated as string type)."""
    manifest = {"outputs": [], "defaults": {}}
    node = {"config": {"outputs": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}}
    assert compile_mod._output_write_keys(node, manifest) == ["a", "b"]


def test_llm_step_spec_reads_extra_inputs_from_manifest_defaults():
    manifest = {
        "defaults": {
            "outputSchema": {"answer": "string"},
            "extraInputs": [{"id": "feedback", "label": "Previous Feedback"}],
        }
    }
    spec = compile_mod._llm_step_spec(_node("n1", "reasoning.cot"), manifest)
    assert spec["extra_inputs"] == [("feedback", "Previous Feedback")]
    assert spec["writes"] == ["answer"]


def test_llm_step_spec_builds_output_model_from_instance_config_ports():
    """Phase B④: a completely empty manifest (custom.node) builds the output model on the fly
    from this node instance's config.outputs — no outputSchema declaration needed."""
    manifest = {"outputs": [], "defaults": {}}
    node = {
        "type": "custom.node",
        "config": {"outputs": [{"id": "summary", "label": "Summary", "dataType": "text"}]},
    }
    spec = compile_mod._llm_step_spec(node, manifest)
    assert spec["writes"] == ["summary"]
    instance = spec["output_model"](summary="hi")
    assert instance.model_dump() == {"summary": "hi"}


async def test_llm_step_node_writes_unknown_output_key_into_vars(monkeypatch):
    """Phase B ②: an output role not in AgentState (a user-defined node type) is stored in
    vars, not at the top level — a key not in AgentState has no LangGraph channel, so
    writing it at the top level would be silently dropped."""
    _patch_model(monkeypatch)
    custom_manifest = {
        "type": "test.custom_writer",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Custom Writer",
        "description": "",
        "inputs": [],
        "outputs": [{"id": "summary", "label": "Summary", "dataType": "text"}],
        "config": [],
        "defaults": {"outputSchema": {"summary": "string"}},
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "test.custom_writer", custom_manifest)

    async def fake_run_llm_step(state, *, node_id, **kwargs):
        return {"summary": "hello"}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_run_llm_step)

    arch = _arch(
        [_node("writer", "test.custom_writer"), _node("output", "io.output")],
        [_edge("writer", "output", "summary", "result")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t-vars"}})

    assert final["vars"] == {"summary": "hello"}


async def test_custom_node_instance_ports_drive_input_reading_and_output_writing(monkeypatch):
    """Phase B④: custom.node has a completely empty manifest, and each instance defines its
    own ports via config.inputs/config.outputs — two instances of the same type must be
    able to have different ports."""
    _patch_model(monkeypatch)
    custom_manifest = {
        "type": "custom.node",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Custom",
        "description": "",
        "inputs": [],
        "outputs": [],
        "config": [],
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "custom.node", custom_manifest)

    captured_input_keys: list[tuple[str, str]] = []

    async def fake_run_llm_step(state, *, node_id, input_keys, **kwargs):
        if node_id == "writer":
            return {"summary": "hi there"}
        if node_id == "reader":
            captured_input_keys.extend(input_keys)
            return {"echo": "read: " + str(state.get("vars", {}).get("summary"))}
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_run_llm_step)

    arch = _arch(
        [
            {
                **_node("writer", "custom.node"),
                "config": {"outputs": [{"id": "summary", "label": "Summary", "dataType": "text"}]},
            },
            {
                **_node("reader", "custom.node"),
                "config": {"inputs": [{"id": "summary", "label": "Summary", "dataType": "text"}]},
            },
            _node("output", "io.output"),
        ],
        [
            _edge("writer", "reader", "summary"),
            _edge("reader", "output", "echo", "result"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t-custom"}})

    assert final["vars"] == {"summary": "hi there", "echo": "read: hi there"}
    assert captured_input_keys == [("summary", "Summary")]


async def test_compile_no_nodes_raises():
    """An architecture with no nodes raises ValueError."""
    with pytest.raises(ValueError, match="no nodes"):
        compile_mod.compile_graph(_arch([], []), DEFAULT_MODEL_CFG, None, "run-1")


async def test_compile_unknown_type_raises():
    """An unregistered node type raises ValueError."""
    arch = _arch([_node("unknown", "foo.bar")], [])
    with pytest.raises(ValueError, match="Unknown node type"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, None, "run-1")


async def test_compile_no_entry_raises(monkeypatch):
    """If every node has an incoming edge (a cycle), ValueError for a missing entry point.

    Cycle validation runs first, so the loop must include a guard to reach this error."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("a", "reasoning.cot"),
            _node("g", "loop.guard", {"onExhaustion": "fail"}),
        ],
        [_edge("a", "g", "answer", "in"), _edge("g", "a", "loopBack", "task")],
    )
    with pytest.raises(ValueError, match="no entry"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


def test_filter_control_edges_unit():
    """An edge from io.input is removed only when the target has a real processing predecessor."""
    nodes = [
        _node("input", "io.input"),
        _node("planning", "planning.decompose"),
        _node("reasoning", "reasoning.cot"),
    ]
    edges = [
        _edge("input", "reasoning"),
        _edge("input", "planning"),
        _edge("planning", "reasoning"),
    ]
    filtered = compile_mod._filter_control_edges(nodes, edges)
    pairs = {(e["source"], e["target"]) for e in filtered}
    assert pairs == {("input", "planning"), ("planning", "reasoning")}


async def test_linear_pipeline_runs(monkeypatch):
    """Compile and run a linear input->planning->reasoning->output pipeline."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "planning", "task"),
            _edge("planning", "reasoning", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t1"}})

    assert final["task"] == "2+2"  # io.input sample seeds the task
    assert final["plan"] == ["s1"]
    assert final["answer"] == "4"
    starts = {e.node_id for e in emitter.events if e.event_type == "node_start"}
    ends = {e.node_id for e in emitter.events if e.event_type == "node_end"}
    assert starts == ends == {"input", "planning", "reasoning", "output"}


async def test_input_prefers_submitted_task_over_canvas_sample(monkeypatch):
    """A task submitted at run time (e.g. over WebSocket) beats the io.input sample."""
    _patch_model(monkeypatch)
    observed_tasks: list[str] = []

    async def capture_task(state, *, node_id, **kwargs):
        observed_tasks.append(state["task"])
        return await fake_llm_step(state, node_id=node_id, **kwargs)

    monkeypatch.setattr(compile_mod, "run_llm_step", capture_task)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "canvas sample"}),
            _node("reasoning", "reasoning.cot"),
        ],
        [_edge("input", "reasoning", "task")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(
        initial_state("submitted task"), {"configurable": {"thread_id": "t3"}}
    )

    assert final["task"] == "submitted task"
    assert observed_tasks == ["submitted task"]
    input_end = next(
        e for e in emitter.events if e.node_id == "input" and e.event_type == "node_end"
    )
    assert input_end.output == {"task": "submitted task"}


async def test_reasoning_direct_no_planning(monkeypatch):
    """input->reasoning->output also works without planning."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),
        ],
        [_edge("input", "reasoning", "task"), _edge("reasoning", "output", "answer")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": "t2"}})
    assert final["answer"] == "4"


async def test_node_positions_do_not_change_compiled_execution(monkeypatch):
    """Canvas coordinates are presentation-only and do not affect the compiled execution order."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    base_nodes = [
        _node("input", "io.input", {"sample": "2+2"}),
        _node("reasoning", "reasoning.cot"),
        _node("output", "io.output"),
    ]
    edges = [_edge("input", "reasoning", "task"), _edge("reasoning", "output", "answer")]
    radial_nodes = [
        {**node, "position": {"x": index * 320 - 160, "y": index * index * 90}}
        for index, node in enumerate(base_nodes)
    ]
    emitters = [ListEventEmitter(), ListEventEmitter()]

    finals = []
    for arch_nodes, emitter, thread_id in zip(
        (base_nodes, radial_nodes), emitters, ("vertical", "radial"), strict=True
    ):
        graph = compile_mod.compile_graph(
            _arch(arch_nodes, edges), DEFAULT_MODEL_CFG, emitter, "run-positions"
        )
        finals.append(
            await graph.ainvoke(initial_state(""), {"configurable": {"thread_id": thread_id}})
        )

    assert [final["answer"] for final in finals] == ["4", "4"]
    event_nodes = [
        [event.node_id for event in emitter.events if event.event_type == "node_start"]
        for emitter in emitters
    ]
    assert event_nodes == [["input", "reasoning", "output"]] * 2


async def test_human_checkpoint_compiles(monkeypatch):
    """An architecture containing human.checkpoint compiles without raising (no invoke)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("checkpoint", "human.checkpoint"),
            _node("output", "io.output"),
        ],
        [_edge("input", "checkpoint", "task"), _edge("checkpoint", "output", "approve")],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
    assert graph is not None


def test_loop_policy_from_config_nests_the_four_scalar_axes():
    node = _node(
        "guard",
        "loop.guard",
        {
            "kind": "critiqueRevise",
            "maxIterations": 3,
            "maxTokens": 1000,
            "maxCostUsd": 0.5,
            "maxDurationSec": 60,
            "onExhaustion": "escalate",
        },
    )
    assert compile_mod._loop_policy_from_config(node) == {
        "id": "guard",
        "onExhaustion": "escalate",
        "guard": {
            "maxIterations": 3,
            "maxTokens": 1000,
            "maxCostUsd": 0.5,
            "maxDurationSec": 60,
        },
    }


def test_loop_policy_from_config_defaults_to_exit_with_an_empty_guard():
    assert compile_mod._loop_policy_from_config(_node("guard", "loop.guard", {})) == {
        "id": "guard",
        "onExhaustion": "exit",
        "guard": {},
    }


def test_loop_policy_from_config_nests_stuck_window_and_threshold():
    node = _node("guard", "loop.guard", {"stuckWindow": 3, "stuckThreshold": 1})
    assert compile_mod._loop_policy_from_config(node)["guard"] == {
        "stuck": {"window": 3, "threshold": 1}
    }


def test_loop_policy_from_config_omits_stuck_threshold_when_unset():
    """Filling threshold with None makes loop_guard._is_stuck's float(None) raise TypeError
    — when unset, the key must be omitted so its default (0) takes effect.
    (loop_guard.py is not to be changed, so this adapter has to match the contract.)"""
    guard = compile_mod._loop_policy_from_config(_node("guard", "loop.guard", {"stuckWindow": 3}))[
        "guard"
    ]

    assert guard == {"stuck": {"window": 3}}
    assert evaluate_loop_guard(
        {"guard": guard},
        {**empty_loop_runtime(), "iteration": 3, "progress_history": [4.0, 4.0, 4.0]},
    ) == {"should_continue": False, "exit_reason": "stuck"}


def _outgoing(edges: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in edges:
        out.setdefault(e["source"], []).append(e)
    return out


def test_derive_loop_members_returns_only_the_refine_loop_body():
    """Starter graph shape: nodes that never return to the guard, like input/output/checkpoint,
    are not budget-attribution targets."""
    edges = [
        _edge("input", "reasoning", "task"),
        _edge("reasoning", "review", "answer"),
        _edge("review", "guard", "refine", "in"),
        _edge("review", "output", "accept", "result"),
        _edge("review", "checkpoint", "clarify", "review"),
        _edge("guard", "reasoning", "loopBack", "task"),
        _edge("guard", "output", "exit", "result"),
        _edge("checkpoint", "output", "approve", "result"),
    ]
    members = compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges))
    assert members == {"reasoning", "review"}


def test_derive_loop_members_covers_a_three_node_body():
    edges = [
        _edge("reasoning", "critic", "answer"),
        _edge("critic", "review", "critique"),
        _edge("review", "guard", "refine", "in"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    assert compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges)) == {
        "reasoning",
        "critic",
        "review",
    }


def test_derive_loop_members_is_empty_without_a_loop_back_target():
    assert compile_mod._derive_loop_members("guard", None, {}) == set()


def test_derive_loop_members_excludes_a_dead_end_branch_inside_the_loop_body():
    """Branches that fork off inside the loop but never return to the guard are excluded."""
    edges = [
        _edge("reasoning", "review", "answer"),
        _edge("review", "guard", "refine", "in"),
        _edge("review", "sink", "accept", "result"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    assert compile_mod._derive_loop_members("guard", "reasoning", _outgoing(edges)) == {
        "reasoning",
        "review",
    }


def _scc_sorted(components: list[list[str]]) -> list[list[str]]:
    return sorted(sorted(component) for component in components)


def test_tarjan_scc_isolates_every_node_when_there_are_no_edges():
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], [])) == [["a"], ["b"], ["c"]]


def test_tarjan_scc_does_not_merge_a_one_way_chain():
    edges = [_edge("a", "b"), _edge("b", "c")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], edges)) == [["a"], ["b"], ["c"]]


def test_tarjan_scc_merges_a_simple_two_cycle():
    edges = [_edge("a", "b"), _edge("b", "a")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b"], edges)) == [["a", "b"]]


def test_tarjan_scc_keeps_a_self_loop_as_a_size_one_component():
    assert _scc_sorted(compile_mod._tarjan_scc(["a"], [_edge("a", "a")])) == [["a"]]


def test_tarjan_scc_merges_two_cycles_that_share_a_node():
    edges = [_edge("a", "b"), _edge("b", "a"), _edge("a", "c"), _edge("c", "a")]
    assert _scc_sorted(compile_mod._tarjan_scc(["a", "b", "c"], edges)) == [["a", "b", "c"]]


def test_validate_gated_cycles_raises_for_an_ungated_cycle():
    with pytest.raises(ValueError, match="Cycle without a loop.guard node"):
        compile_mod._validate_gated_cycles(["a", "b"], [_edge("a", "b"), _edge("b", "a")], set())


def test_validate_gated_cycles_accepts_a_cycle_containing_a_guard():
    compile_mod._validate_gated_cycles(["a", "g"], [_edge("a", "g"), _edge("g", "a")], {"g"})


def test_validate_gated_cycles_ignores_self_loops():
    """SCCs of size 1 (including self-loops) are not subject to gating (design §non-goals)."""
    compile_mod._validate_gated_cycles(["a"], [_edge("a", "a")], set())


def test_validate_gated_cycles_reports_only_the_ungated_component():
    edges = [
        _edge("a", "g"),
        _edge("g", "a"),
        _edge("c", "d"),
        _edge("d", "c"),
    ]
    with pytest.raises(ValueError, match=r"\['c', 'd'\]"):
        compile_mod._validate_gated_cycles(["a", "g", "c", "d"], edges, {"g"})


def test_validate_gated_cycles_rejects_an_ungated_cycle_sharing_a_node_with_a_gated_one():
    """Tarjan merges cycles that share a node into one component — a cycle drawn without a guard
    must not silently pass just because it shares a single node with a guarded cycle."""
    edges = [
        _edge("reasoning", "review"),
        _edge("review", "guard"),
        _edge("guard", "reasoning"),
        _edge("reasoning", "critic"),
        _edge("critic", "reasoning"),
    ]
    with pytest.raises(ValueError, match=r"\['critic', 'reasoning'\]"):
        compile_mod._validate_gated_cycles(
            ["reasoning", "review", "guard", "critic"], edges, {"guard"}
        )


def test_validate_gated_cycles_still_accepts_a_purely_gated_cycle():
    edges = [_edge("a", "g"), _edge("g", "a")]
    compile_mod._validate_gated_cycles(["a", "g"], edges, {"g"})


async def test_loop_guard_without_a_loop_back_edge_raises(monkeypatch):
    """A Loop node with no loopBack wired is a 'loop that goes nowhere' — a config mistake (§9).

    The "review" node here is merely the source of two edges heading to guard/output
    (unrelated to review.intent's 3-way branch validation) — reasoning.cot is enough."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "reasoning.cot"),
            _node("guard", "loop.guard", {"onExhaustion": "fail"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
        ],
    )
    with pytest.raises(ValueError, match="no 'loopBack' edge"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_exit_port_unwired_raises(monkeypatch):
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "reasoning.cot"),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
        ],
    )
    with pytest.raises(ValueError, match="requires a wired 'exit' port"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_loopback_port_fanout_raises(monkeypatch):
    """With two or more outgoing edges on the loopBack port, _handle_targets keeps only the last
    and silently drops the rest, so it must be blocked with a compile error."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "reasoning.cot"),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "review", "loopBack", "in"),
            _edge("guard", "output", "exit", "result"),
        ],
    )
    with pytest.raises(ValueError, match=r"2 edges assigned the 'loopBack' role"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_exit_port_fanout_raises(monkeypatch):
    """Like loopBack, two or more outgoing edges on the exit port is a compile error."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "reasoning.cot"),
            _node("guard", "loop.guard", {"onExhaustion": "exit"}),
            _node("output", "io.output"),
            _node("output2", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "guard", "refine", "in"),
            _edge("review", "output", "accept", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
            _edge("guard", "output2", "exit", "result"),
        ],
    )
    with pytest.raises(ValueError, match=r"2 edges assigned the 'exit' role"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_review_unassigned_branch_edge_raises_at_compile(monkeypatch):
    """An edge drawn freeform whose role has not yet been picked in the Inspector must be blocked
    at compile time — the problem was that, like human.checkpoint, it silently fell to END
    (review.intent was retired by the 2026-09-02 text-first switch, so this is verified with
    human.checkpoint, which goes through the same _validate_branch_roles path)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "human.checkpoint"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "output", source_handle="opaque-slot-1"),  # role unassigned
        ],
    )
    with pytest.raises(ValueError, match="unassigned or unknown"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_invalid_on_exhaustion_raises(monkeypatch):
    _patch_model(monkeypatch)
    arch = _gated_refine_arch({"onExhaustion": "retry-forever"})
    with pytest.raises(ValueError, match="invalid onExhaustion"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_loop_guard_max_iterations_trips_to_the_exit_port(monkeypatch):
    """Even if the reviewer keeps picking refine, the guard's maxIterations=2 trips and exits."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxIterations": 2}), DEFAULT_MODEL_CFG, emitter, "run-1"
    )
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="accurate calculation"),
        {"configurable": {"thread_id": "t-loop-iter"}},
    )

    assert final["answer"] == "4"
    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2, 3]
    # The guard node is a real canvas node, so nodeId == loopNodeId (design §8).
    assert {e.loop_runtime["loopNodeId"] for e in guard_events} == {"guard"}
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"
    assert guard_events[-1].loop_runtime["maxIterations"] == 2


async def test_loop_guard_on_exhaustion_fail_raises_at_runtime(monkeypatch):
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxIterations": 1, "onExhaustion": "fail"}),
        DEFAULT_MODEL_CFG,
        ListEventEmitter(),
        "run-1",
    )
    with pytest.raises(RuntimeError, match="onExhaustion='fail'"):
        await graph.ainvoke(
            initial_state("", criteria=_ONE_CRITERION, intent="accurate calculation"),
            {"configurable": {"thread_id": "t-loop-fail"}},
        )


async def test_loop_guard_max_tokens_trips_using_derived_members(monkeypatch):
    """reasoning/reviewer are derived as loop members and add tokens to loop_runtime['guard']."""
    _patch_model(monkeypatch)

    async def reasoning_with_usage(state, *, node_id, usage_sink=None, **kwargs):
        if node_id == "reviewer":
            return {"verdict": "unmet", "route": "refine"}
        if usage_sink is not None:
            usage_sink["prompt"] = 400
            usage_sink["completion"] = 200
            usage_sink["cost"] = 0.02
        return {"answer": "4", "confidence": 0.9}

    monkeypatch.setattr(compile_mod, "run_llm_step", reasoning_with_usage)
    emitter = ListEventEmitter()

    graph = compile_mod.compile_graph(
        _gated_refine_arch({"maxTokens": 1000}), DEFAULT_MODEL_CFG, emitter, "run-1"
    )
    final = await graph.ainvoke(
        initial_state("", criteria=_ONE_CRITERION, intent="accurate calculation"),
        {"configurable": {"thread_id": "t-loop-tokens"}},
    )

    assert final["answer"] == "4"
    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert guard_events[-1].loop_runtime["exitReason"] == "budget"
    assert guard_events[-1].loop_runtime["tokens"] >= 1000


async def test_loop_guard_is_reached_from_human_checkpoint_dynamic_goto(monkeypatch):
    """human.checkpoint is skipped entirely in the edge-wiring loop and branches only via
    Command(goto=...) — a real interrupt/resume cycle proves that the guard node is reached
    only by dynamic goto, with neither a static edge nor a declared branch mapping."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("checkpoint", "human.checkpoint"),
            _node("guard", "loop.guard", {"maxIterations": 1, "onExhaustion": "exit"}),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "checkpoint", "answer", "review"),
            _edge("checkpoint", "guard", "revise", "in"),
            _edge("checkpoint", "output", "approve", "result"),
            _edge("guard", "reasoning", "loopBack", "task"),
            _edge("guard", "output", "exit", "result"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    config = {"configurable": {"thread_id": "t-loop-checkpoint"}}

    first = await graph.ainvoke(initial_state(""), config)
    assert first.get("__interrupt__")

    second = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert second.get("__interrupt__")

    final = await graph.ainvoke(Command(resume={"action": "revise"}), config)
    assert not final.get("__interrupt__")
    assert final["answer"] == "4"

    guard_events = [e for e in emitter.events if e.node_id == "guard" and e.loop_runtime]
    assert [e.loop_runtime["iteration"] for e in guard_events] == [1, 2]
    assert guard_events[-1].loop_runtime["exitReason"] == "maxIterations"


async def test_cycle_without_loop_guard_raises(monkeypatch):
    """A direct review --refine--> reasoning loop is now a compile error (design §4, an intended
    breaking change — a Loop node must be inserted for it to compile)."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("reasoning", "reasoning.cot"),
            _node("review", "review.intent"),
            _node("output", "io.output"),
        ],
        [
            _edge("input", "reasoning", "task"),
            _edge("reasoning", "review", "answer"),
            _edge("review", "reasoning", "refine", "task"),
            _edge("review", "output", "accept", "result"),
        ],
    )
    with pytest.raises(ValueError, match="Cycle without a loop.guard node"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_cycle_with_loop_guard_compiles(monkeypatch):
    _patch_model(monkeypatch)
    graph = compile_mod.compile_graph(
        _gated_refine_arch({}), DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1"
    )
    assert graph is not None


def test_validate_required_inputs_passes_when_preseeded_key_has_no_writer_node():
    """task is always filled by initial_state(), so reasoning.cot's required task counts as
    satisfied even if there is no io.input node in the graph (design §6, Tier 1)."""
    nodes = [_node("reasoning", "reasoning.cot"), _node("output", "io.output")]
    compile_mod._validate_required_inputs(nodes)  # must pass without raising


def test_validate_required_inputs_passes_when_a_writer_exists():
    nodes = [_node("planning", "planning.decompose"), _node("reasoning", "reasoning.cot")]
    compile_mod._validate_required_inputs(nodes)  # must pass without raising


def test_validate_required_inputs_raises_when_no_node_writes_a_required_non_preseeded_key(
    monkeypatch,
):
    """Today's real manifests have no such case (every required input is preseeded), so a
    synthetic llm_step type is injected to reproduce it."""
    fake_manifest = {
        "type": "test.needs_summary",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Needs Summary",
        "description": "",
        "inputs": [{"id": "summary", "label": "Summary", "dataType": "text", "required": True}],
        "outputs": [],
        "config": [],
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "test.needs_summary", fake_manifest)
    nodes = [_node("n1", "test.needs_summary")]
    with pytest.raises(ValueError, match="requires input 'summary'"):
        compile_mod._validate_required_inputs(nodes)


async def test_compile_graph_raises_for_missing_required_input(monkeypatch):
    """Check that _validate_required_inputs is actually wired into compile_graph — it must run
    before node creation/model resolution so it blocks before any execution cost is incurred."""
    fake_manifest = {
        "type": "test.needs_summary",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Needs Summary",
        "description": "",
        "inputs": [{"id": "summary", "label": "Summary", "dataType": "text", "required": True}],
        "outputs": [],
        "config": [],
    }
    monkeypatch.setitem(compile_mod.MANIFESTS_BY_TYPE, "test.needs_summary", fake_manifest)
    arch = _arch([_node("n1", "test.needs_summary")], [])
    with pytest.raises(ValueError, match="requires input 'summary'"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, None, "run-1")


def test_build_plain_edge_plan_single_source_is_not_joined():
    nodes = [_node("a", "reasoning.cot"), _node("b", "io.output")]
    edges = [_edge("a", "b", "answer")]
    assert compile_mod._build_plain_edge_plan(nodes, edges) == [(["a"], "b")]


def test_build_plain_edge_plan_requires_join_mode_for_two_plain_sources():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        _node("c", "io.output"),  # joinMode undeclared
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)


def test_build_plain_edge_plan_creates_a_single_join_edge_for_and():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "and"},
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["a", "b"], "c")]


def test_build_plain_edge_plan_keeps_individual_edges_for_or():
    nodes = [
        _node("a", "planning.decompose"),
        _node("b", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "or"},
    ]
    edges = [_edge("a", "c", "plan"), _edge("b", "c", "answer")]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert sorted(plan) == [(["a"], "c"), (["b"], "c")]


def test_build_plain_edge_plan_forces_or_when_a_conditional_source_is_mixed_in():
    """If even one conditional-routing source such as review.intent/loop.guard/human.checkpoint
    is mixed in, AND is structurally impossible — these three route themselves via
    add_conditional_edges or Command(goto=...) and never call add_edge, so they cannot take part
    in a LangGraph join-edge. No joinMode declaration is required, and the remaining plain
    sources automatically become individual edges (design §4)."""
    nodes = [
        _node("input", "io.input"),
        _node("guard", "loop.guard"),
        _node("reasoning", "reasoning.cot"),  # must not error even with joinMode undeclared
    ]
    edges = [
        _edge("input", "reasoning", "task"),
        _edge("guard", "reasoning", "loopBack", "task"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["input"], "reasoning")]  # the edge from guard never enters the plan at all


def test_build_plain_edge_plan_still_requires_join_mode_for_two_plain_passthrough_sources():
    """Passthrough types other than loop.reentry (io.input/io.output/model.binding) are not part
    of this exception — when two or more actually converge, joinMode is still required."""
    nodes = [
        _node("a", "io.input"),
        _node("b", "model.binding"),
        _node("target", "io.output"),  # joinMode undeclared — must error
    ]
    edges = [_edge("a", "target"), _edge("b", "target")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)


def test_build_plain_edge_plan_raises_cleanly_for_a_dangling_edge_target():
    """If the target is not in the nodes list (a node was deleted on the freeform canvas but an
    edge that pointed to it remains), it must be handled defensively, the same as the source
    lookup — it must not die with KeyError but be absorbed naturally into the existing
    'config error' (missing joinMode) ValueError."""
    nodes = [_node("a", "planning.decompose"), _node("b", "reasoning.cot")]
    edges = [_edge("a", "missing", "plan"), _edge("b", "missing", "answer")]
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod._build_plain_edge_plan(nodes, edges)


def test_build_plain_edge_plan_excludes_conditional_sourced_edges_entirely():
    nodes = [_node("checkpoint", "human.checkpoint"), _node("output", "io.output")]
    edges = [_edge("checkpoint", "output", "approve")]
    assert compile_mod._build_plain_edge_plan(nodes, edges) == []


def test_build_plain_edge_plan_forces_or_with_two_plain_sources_and_a_conditional_source():
    """If even one conditional-routing source is mixed in, AND is structurally impossible even
    with two or more plain sources — it must be handled as individual edges without error and
    without a joinMode declaration (the key scenario of design §4: in the starter architecture,
    the guard converges on one target together with other plain sources)."""
    nodes = [
        _node("planning", "planning.decompose"),
        _node("reasoning", "reasoning.cot"),
        _node("guard", "loop.guard"),
        _node("target", "io.output"),  # must not error even with joinMode undeclared
    ]
    edges = [
        _edge("planning", "target", "plan"),
        _edge("reasoning", "target", "answer"),
        _edge("guard", "target", "loopBack", "task"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert sorted(plan) == [(["planning"], "target"), (["reasoning"], "target")]


def test_build_plain_edge_plan_dedups_multiple_edges_from_the_same_source_target_pair():
    """Even when multiple edges come from the same (source, target) pair (e.g. connected twice
    through different data ports), the source must be counted only once — it must appear
    only once in the joined source list, with no duplicates."""
    nodes = [
        _node("a", "planning.decompose"),
        _node("d", "reasoning.cot"),
        {**_node("c", "io.output"), "joinMode": "and"},
    ]
    edges = [
        _edge("a", "c", "plan1", "in1"),
        _edge("a", "c", "plan2", "in2"),
        _edge("d", "c", "answer"),
    ]
    plan = compile_mod._build_plain_edge_plan(nodes, edges)
    assert plan == [(["a", "d"], "c")]


async def test_compile_graph_requires_join_mode_for_two_plain_sources(monkeypatch):
    """Check that _build_plain_edge_plan is actually wired into compile_graph — if two or more
    plain sources converge on one target and there is no joinMode, it must be a compile error."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            _node("output", "io.output"),  # joinMode undeclared
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    with pytest.raises(ValueError, match="no joinMode"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_compile_graph_and_join_compiles_and_runs(monkeypatch):
    """Declaring joinMode='and' compiles to a join-edge with no compile error, and runs to
    completion with the results of both plain sources (planning/reasoning) reflected in the
    final state."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            {**_node("output", "io.output"), "joinMode": "and"},
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state("2+2"), {"configurable": {"thread_id": "t-and"}})
    assert final.get("plan") == ["s1"]
    assert final.get("answer") == "4"


async def test_compile_graph_or_join_still_compiles_and_runs(monkeypatch):
    """joinMode='or' still compiles and runs — individual add_edge as before (regression)."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    emitter = ListEventEmitter()
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            {**_node("output", "io.output"), "joinMode": "or"},
        ],
        [
            _edge("input", "planning", "task"),
            _edge("input", "reasoning", "task"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, emitter, "run-1")
    final = await graph.ainvoke(initial_state("2+2"), {"configurable": {"thread_id": "t-or"}})
    assert final.get("plan") == ["s1"]
    assert final.get("answer") == "4"


def test_branch_labels_needs_two_labelled_edges():
    """Branch detection is by the number of labelled outgoing edges (design §5), not by type —
    only a node with two or more sourceRoles filled in is a branch node."""
    edges = [
        {"source": "a", "target": "b", "sourceRole": "ok"},
        {"source": "a", "target": "c", "sourceRole": "no"},
        {"source": "b", "target": "c", "sourceRole": ""},
    ]
    assert compile_mod._branch_labels("a", edges) == ["ok", "no"]
    assert compile_mod._branch_labels("b", edges) == []


def test_branch_labels_ignores_unlabelled_fanout():
    """A fan-out without labels (sourceRole == "") is parallel execution, not a branch."""
    edges = [
        {"source": "a", "target": "b", "sourceRole": ""},
        {"source": "a", "target": "c", "sourceRole": ""},
    ]
    assert compile_mod._branch_labels("a", edges) == []


def test_branch_labels_ignores_source_handle_fallback():
    """Old-canvas architectures have only sourceHandle, with no sourceRole (a port name, e.g.
    "plan"/"answer") — falling back to sourceHandle like _resolved_role would misread every
    ordinary fan-out as a branch. _branch_labels must look at sourceRole only."""
    edges = [
        {"source": "a", "target": "b", "sourceHandle": "plan"},
        {"source": "a", "target": "c", "sourceHandle": "answer"},
    ]
    assert compile_mod._branch_labels("a", edges) == []


def test_user_node_with_labels_gets_route_field_in_output_model():
    """Passing branch_labels to _effective_output_schema adds a route field holding the label
    list as-is — _build_output_model turns it into a Literal."""
    from archfile import parse_arch

    arch, _ = parse_arch(
        """
flow: |
  input --> judge
  judge -->|good| output
  judge -->|bad| output2
nodes:
  judge:   { in: [task], out: [verdict], prompt: p }
  output2: { run: output }
"""
    )
    node = next(n for n in arch["nodes"] if n["id"] == "judge")
    schema = compile_mod._effective_output_schema(
        node, compile_mod.MANIFESTS_BY_TYPE[node["type"]], branch_labels=["good", "bad"]
    )
    assert schema["verdict"] == "string"
    assert schema["route"] == ["good", "bad"]


def test_build_output_model_turns_label_list_into_literal():
    """The route field (list value) becomes a Literal[...], so the LLM can emit only one label."""
    model = compile_mod._build_output_model(
        "custom.node", {"verdict": "string", "route": ["good", "bad"]}
    )
    instance = model(verdict="ok", route="good")
    assert instance.model_dump() == {"verdict": "ok", "route": "good"}
    with pytest.raises(ValidationError):
        model(verdict="ok", route="unknown")


async def test_branching_user_node_compiles(monkeypatch):
    """A user-defined node (custom.node) that fans out with 2 labels compiles as a branch node
    — branching must work even when it is not review.intent/human.checkpoint/loop.guard."""
    from archfile import parse_arch

    _patch_model(monkeypatch)
    arch, _ = parse_arch(
        """
flow: |
  input --> judge
  judge -->|good| output
  judge -->|bad| rework
  rework --> output
nodes:
  judge:   { in: [task], out: [verdict], prompt: p }
  rework: { in: [task], out: [answer], prompt: q }
"""
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "r1")
    assert graph is not None


async def test_branching_user_node_routes_on_llm_pick(monkeypatch):
    """If the branch node picks "bad" via route it goes to the rework node, and if it picks
    "good" it goes to output — execution also confirms the router reads the __route__<id>
    state key."""
    from archfile import parse_arch

    _patch_model(monkeypatch)

    async def fake_run_llm_step(state, *, node_id, **kwargs):
        if node_id == "judge":
            return {"verdict": "meh", "route": "bad"}
        if node_id == "rework":
            return {"answer": "fixed"}
        return {}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake_run_llm_step)

    arch, _ = parse_arch(
        """
flow: |
  input --> judge
  judge -->|good| output
  judge -->|bad| rework
  rework --> output
nodes:
  judge:   { in: [task], out: [verdict], prompt: p }
  rework: { in: [task], out: [answer], prompt: q }
"""
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "r1")
    final = await graph.ainvoke(initial_state("task"), {"configurable": {"thread_id": "t-branch"}})
    assert final["vars"]["verdict"] == "meh"
    assert final.get("answer") == "fixed"


async def test_labelled_fanout_from_non_llm_step_node_still_runs_both(monkeypatch):
    """Even if a node that is not llm_step (has no structured output), like io.input, happens to
    carry 2 descriptive labels, it must not be mistaken for a branch — nobody writes
    __route__<id>, so the router would always fall to the first label and the other side
    would silently never run.
    branch_node_ids must target only runtime == "llm_step" nodes."""
    _patch_model(monkeypatch)
    monkeypatch.setattr(compile_mod, "run_llm_step", fake_llm_step)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node("planning", "planning.decompose"),
            _node("reasoning", "reasoning.cot"),
            {**_node("output", "io.output"), "joinMode": "and"},
        ],
        [
            _edge("input", "planning", source_role="a"),
            _edge("input", "reasoning", source_role="b"),
            _edge("planning", "output", "plan"),
            _edge("reasoning", "output", "answer"),
        ],
    )
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")
    final = await graph.ainvoke(initial_state("2+2"), {"configurable": {"thread_id": "t-fanout"}})
    assert final.get("plan") == ["s1"]
    assert final.get("answer") == "4"


async def test_duplicate_branch_label_raises_at_compile(monkeypatch):
    """In a raw architecture dict (the same shape the canvas saves without parse_arch), if a
    branch node's two outgoing edges use the same label ("ok"), one is silently collapsed in
    the dict comprehension targets = {label: target ...} — the parser-side check in archfile.py
    (_validate_branch_capable) cannot protect this path, which bypasses parse_arch, so
    compile_graph itself has to block this duplicate."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node(
                "judge",
                "custom.node",
                {
                    "systemPrompt": "p",
                    "inputs": [{"id": "task", "label": "task"}],
                    "outputs": [{"id": "verdict", "label": "verdict"}],
                },
            ),
            _node("output", "io.output"),
            _node("other", "io.output"),
        ],
        [
            _edge("input", "judge", "task"),
            _edge("judge", "output", source_role="ok"),
            _edge("judge", "other", source_role="ok"),
        ],
    )
    with pytest.raises(ValueError, match="ok"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_branch_node_with_unlabelled_edge_raises_at_compile(monkeypatch):
    """If a branch node (with two or more labelled outgoing edges) has even one more outgoing
    edge without a label, that edge is caught nowhere — neither in _build_plain_edge_plan (the
    source is in branch_node_ids, so excluded) nor in add_conditional_edges' targets dict (no
    sourceRole, so not matched) — and silently disappears (BLOCKING 1). dispatch_graph in
    main.py hands the raw architecture dict saved from the canvas straight here without the
    archfile.py parser, so compile_graph itself has to reject this path."""
    _patch_model(monkeypatch)
    arch = _arch(
        [
            _node("input", "io.input", {"sample": "2+2"}),
            _node(
                "judge",
                "custom.node",
                {
                    "systemPrompt": "p",
                    "inputs": [{"id": "task", "label": "task"}],
                    "outputs": [{"id": "verdict", "label": "verdict"}],
                },
            ),
            _node("output", "io.output"),
            _node(
                "fix",
                "custom.node",
                {
                    "systemPrompt": "q",
                    "inputs": [{"id": "task", "label": "task"}],
                    "outputs": [{"id": "answer", "label": "answer"}],
                },
            ),
            _node("logger", "io.output"),
        ],
        [
            _edge("input", "judge", "task"),
            _edge("judge", "output", source_role="ok"),
            _edge("judge", "fix", source_role="retry"),
            _edge("judge", "logger"),  # no sourceRole — silently disappears today
            _edge("fix", "output"),
        ],
    )
    with pytest.raises(ValueError, match="judge"):
        compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "run-1")


async def test_yaml_fan_in_with_join_all_runs_judge_once(monkeypatch):
    from archfile import parse_arch
    from tests.arch_samples import FAN_IN

    monkeypatch.setattr(compile_mod, "build_model", lambda settings: None)
    calls = []

    async def fake(state, *, node_id, output_model, **_):
        calls.append(node_id)
        return {k: f"{node_id}:{k}" for k in output_model.model_fields}

    monkeypatch.setattr(compile_mod, "run_llm_step", fake)
    arch, _ = parse_arch(FAN_IN % ", join: all")
    graph = compile_mod.compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "r")
    await graph.ainvoke(initial_state("t"), {"configurable": {"thread_id": "fan-in"}})
    assert calls.count("judge") == 1


def test_missing_join_mode_error_points_to_yaml_not_inspector():
    from archfile import parse_arch
    from tests.arch_samples import FAN_IN

    arch, _ = parse_arch(FAN_IN % ", join: all")
    for n in arch["nodes"]:
        n.pop("joinMode", None)
    with pytest.raises(ValueError) as e:
        compile_mod._build_plain_edge_plan(arch["nodes"], arch["edges"])
    assert "join:" in str(e.value) and "Inspector" not in str(e.value)
