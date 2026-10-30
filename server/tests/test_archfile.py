import pytest

from archfile import ArchError, parse_arch, parse_flow
from graphs.compile import compile_graph


def test_simple_chain_splits_into_edges():
    edges = parse_flow("a --> b --> c")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [
        ("a", "b", ""),
        ("b", "c", ""),
    ]


def test_labelled_edge_keeps_label_verbatim():
    edges = parse_flow("review -->|retry| reasoning")
    assert edges[0] == {
        "source": "review",
        "target": "reasoning",
        "label": "retry",
        "line": 1,
    }


def test_blank_lines_and_comments_ignored():
    edges = parse_flow("a --> b\n\n%% comment\n  \nb --> c")
    assert len(edges) == 2
    assert edges[1]["line"] == 5


def test_unicode_node_names_allowed():
    edges = parse_flow("intake --> draft --> done")
    assert [e["source"] for e in edges] == ["intake", "draft"]


def test_malformed_line_raises_with_line_number():
    with pytest.raises(ArchError) as exc:
        parse_flow("a --> b\nthis is not an edge")
    assert exc.value.line == 2
    assert "this is not an edge" in str(exc.value)


def test_label_only_on_first_hop_of_chain():
    edges = parse_flow("a -->|go| b --> c")
    assert edges[0]["label"] == "go"
    assert edges[1]["label"] == ""


def test_leading_flowchart_directive_is_skipped():
    """item 5 (§3.2): pasting a `flow:` block as-is into GitHub/Obsidian etc. to render it as
    mermaid needs a header like `flowchart LR`, but that line has no arrow, so the
    parser used to reject it as "expected '-->'" — the `flowchart`/`graph` directive is now
    skipped for the first line only."""
    edges = parse_flow("flowchart LR\n  a --> b")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [("a", "b", "")]


def test_leading_graph_directive_is_skipped():
    """mermaid's legacy `graph` directive (an alias of `flowchart`) is also skipped on the first
    line."""
    edges = parse_flow("graph TD\n  a --> b")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [("a", "b", "")]


def test_flowchart_directive_only_skipped_as_first_line():
    """The directive is valid only on the first line — it must not swallow even the extreme
    case of using "flowchart" as a node name."""
    with pytest.raises(ArchError):
        parse_flow("a --> b\nflowchart LR")


def test_unspaced_arrow_without_label():
    edges = parse_flow("a-->b")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [
        ("a", "b", ""),
    ]


def test_unspaced_arrow_with_label():
    edges = parse_flow("a-->|go|b")
    assert edges[0] == {
        "source": "a",
        "target": "b",
        "label": "go",
        "line": 1,
    }


def test_hyphen_in_node_name():
    edges = parse_flow("my-node --> other-node")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [
        ("my-node", "other-node", ""),
    ]


def test_trailing_arrow_raises():
    with pytest.raises(ArchError) as exc:
        parse_flow("a --> b -->")
    assert exc.value.line == 1
    assert "trailing arrow" in str(exc.value)


STARTER = """
name: test graph
model: google/gemini-3.1-flash-lite

flow: |
  input --> draft --> review --> output

nodes:
  draft:
    in:  [task]
    out: [draft]
    prompt: Answer quickly.
  review:
    in:  [task, draft]
    out: [answer]
    model: anthropic/claude-opus-5
    prompt: Find the flaws and fix them.
"""


def test_user_nodes_become_custom_node_type():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["draft"]["type"] == "custom.node"
    assert by_id["draft"]["config"]["systemPrompt"] == "Answer quickly."
    assert by_id["draft"]["config"]["outputs"] == [{"id": "draft", "label": "draft"}]
    assert by_id["draft"]["config"]["inputs"] == [{"id": "task", "label": "task"}]


def test_boundary_nodes_get_predefined_types():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["input"]["type"] == "io.input"
    assert by_id["output"]["type"] == "io.output"


def test_node_model_overrides_default():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["draft"]["config"]["modelSlots"][0]["model"] == "gemini-3.1-flash-lite"
    assert by_id["draft"]["config"]["modelSlots"][0]["provider"] == "google"
    assert by_id["review"]["config"]["modelSlots"][0]["model"] == "claude-opus-5"
    assert by_id["review"]["config"]["modelSlots"][0]["provider"] == "anthropic"


def test_edges_carry_label_as_source_role():
    arch, _ = parse_arch("""
flow: |
  a -->|ok| b
nodes:
  a: { out: [x], prompt: p }
  b: { in: [x], out: [y], prompt: q }
""")
    e = arch["edges"][0]
    assert e["source"] == "a"
    assert e["target"] == "b"
    assert e["sourceRole"] == "ok"
    assert e["sourceHandle"] == "ok"


def test_flow_node_missing_from_nodes_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> ghost
nodes:
  a: { out: [x], prompt: p }
""")
    assert "ghost" in str(exc.value)
    assert exc.value.line == 3


def test_input_name_with_no_producer_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b: { in: [missing], out: [y], prompt: q }
""")
    assert "missing" in str(exc.value)


def test_feedback_loop_input_with_no_upstream_producer_in_flow_order_parses():
    # reasoning comes before review in flow order, but review produces the feedback later
    # — a normal case of feedback returning through a loop (design §5.1), not a typo.
    arch, _ = parse_arch("""
flow: |
  a --> reasoning --> review --> output
nodes:
  a: { out: [task], prompt: p }
  reasoning: { in: [task, feedback], out: [answer], prompt: q }
  review: { in: [answer], out: [feedback], prompt: r }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["reasoning"]["config"]["inputs"] == [
        {"id": "task", "label": "task"},
        {"id": "feedback", "label": "feedback"},
    ]


def test_prompt_text_resembling_yaml_syntax_round_trips_byte_for_byte():
    # The deleted '?' preprocessing used to touch the whole original text — now that there is no
    # preprocessing,
    # neither prompt text mimicking in:/out: syntax nor natural-language question marks should be
    # touched.
    arch, _ = parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b:
    in:  [x]
    out: [y]
    prompt: "As promised, may I use the in: [a?, b] out: [c?] form? Really?"
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert (
        by_id["b"]["config"]["systemPrompt"]
        == "As promised, may I use the in: [a?, b] out: [c?] form? Really?"
    )


def test_duplicate_output_name_warns_but_parses():
    arch, warnings = parse_arch("""
flow: |
  a --> b --> output
nodes:
  a: { out: [answer], prompt: p }
  b: { in: [answer], out: [answer], prompt: q }
""")
    assert arch is not None
    assert any("answer" in w for w in warnings)


def test_predefined_run_node():
    arch, _ = parse_arch("""
flow: |
  a --> approval --> output
nodes:
  a: { out: [x], prompt: p }
  approval: { run: human.checkpoint }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["approval"]["type"] == "human.checkpoint"


def test_unknown_run_value_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b: { run: no.such.thing }
""")
    assert "no.such.thing" in str(exc.value)


def test_node_order_follows_flow_first_appearance():
    arch, _ = parse_arch("""
flow: |
  input --> b --> c --> output
nodes:
  b: { in: [task], out: [x], prompt: p }
  c: { in: [x], out: [y], prompt: q }
""")
    assert [n["id"] for n in arch["nodes"]] == ["input", "b", "c", "output"]


async def _noop_emit(_event):
    return None


def test_parsed_arch_compiles_with_compile_graph():
    arch, _ = parse_arch(STARTER)
    graph = compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _noop_emit,
        "test-run",
    )
    assert graph is not None


LOOPED = """
flow: |
  input --> solve --> review
  review -->|ok|    output
  review -->|retry| solve

nodes:
  solve:  { in: [task, feedback], out: [answer], prompt: Solve it }
  review:  { in: [task, answer],    out: [verdict, feedback], prompt: Review it }
"""


def test_back_edge_gets_default_guard_inserted():
    arch, _ = parse_arch(LOOPED)
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert len(guards) == 1
    assert guards[0]["id"] == "__guard_1"
    assert guards[0]["config"]["maxIterations"] == 3


def test_inserted_guard_is_wired_between_and_to_terminal():
    arch, _ = parse_arch(LOOPED)
    by_src = {}
    for e in arch["edges"]:
        by_src.setdefault(e["source"], []).append(e)
    # review --retry--> now goes to __guard_1 and does not go directly to solve
    retry = [e for e in by_src["review"] if e["sourceRole"] == "retry"][0]
    assert retry["target"] == "__guard_1"
    guard_targets = {e["sourceRole"]: e["target"] for e in by_src["__guard_1"]}
    assert guard_targets == {"loopBack": "solve", "exit": "output"}


def test_explicit_guard_is_left_alone():
    arch, _ = parse_arch("""
flow: |
  input --> solve --> review
  review -->|ok|    output
  review -->|retry| retry5
  retry5 -->|loopBack| solve
  retry5 -->|exit|     output
nodes:
  solve:   { in: [task], out: [answer], prompt: p }
  review:   { in: [answer], out: [verdict], prompt: q }
  retry5: { run: loop.guard, max: 5 }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert [g["id"] for g in guards] == ["retry5"]
    assert guards[0]["config"]["maxIterations"] == 5


def test_ambiguous_exit_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input --> solve --> review
  review -->|a| out1
  review -->|b| out2
  review -->|retry| solve
nodes:
  solve: { in: [task], out: [answer], prompt: p }
  review: { in: [answer], out: [v], prompt: q }
  out1: { run: output }
  out2: { run: output }
""")
    assert "exit" in str(exc.value).lower()


def test_looped_arch_compiles():
    arch, _ = parse_arch(LOOPED)
    graph = compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _noop_emit,
        "test-run",
    )
    assert graph is not None


def test_diamond_fan_in_is_not_mistaken_for_a_loop():
    # Pure fan-in: a and b each converge on c. In first-appearance order from flow it is
    # (input, a, c, b, output), so b --> c looks like it "goes backward", yet there is no cycle at
    # all.
    arch, _ = parse_arch("""
flow: |
  input --> a --> c
  input --> b --> c
  c --> output
nodes:
  a: { in: [task], out: [x], prompt: p }
  b: { in: [task], out: [y], prompt: q }
  c: { in: [x, y], out: [z], prompt: r }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert guards == []
    pairs = [(e["source"], e["target"]) for e in arch["edges"]]
    assert pairs == [
        ("input", "a"),
        ("a", "c"),
        ("input", "b"),
        ("b", "c"),
        ("c", "output"),
    ]


def test_three_node_cycle_gets_exactly_one_guard():
    arch, _ = parse_arch("""
flow: |
  input --> a --> b --> c --> a
  c --> output
nodes:
  a: { in: [task], out: [x], prompt: p }
  b: { in: [x], out: [y], prompt: q }
  c: { in: [y], out: [z], prompt: r }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert len(guards) == 1


def test_two_independent_loops_get_separately_numbered_guards():
    arch, _ = parse_arch("""
flow: |
  input --> a --> b
  b -->|ok|     output
  b -->|retry1| a
  input --> c --> d
  d -->|ok2|    output
  d -->|retry2| c
nodes:
  a: { in: [task], out: [x], prompt: p }
  b: { in: [x], out: [y], prompt: q }
  c: { in: [task], out: [m], prompt: r }
  d: { in: [m], out: [n], prompt: s }
""")
    guards = {n["id"]: n for n in arch["nodes"] if n["type"] == "loop.guard"}
    assert set(guards) == {"__guard_1", "__guard_2"}
    by_src = {}
    for e in arch["edges"]:
        by_src.setdefault(e["source"], []).append(e)
    guard1_targets = {e["sourceRole"]: e["target"] for e in by_src["__guard_1"]}
    guard2_targets = {e["sourceRole"]: e["target"] for e in by_src["__guard_2"]}
    assert guard1_targets == {"loopBack": "a", "exit": "output"}
    assert guard2_targets == {"loopBack": "c", "exit": "output"}


def test_cycle_in_unreachable_component_is_still_detected():
    # input->output is fully visited and finished from the first DFS root. The x/y cycle is a
    # separate
    # component unreachable from there, so it is missed unless every root is iterated in nodes
    # order.
    arch, _ = parse_arch("""
flow: |
  input --> output
  x --> y --> x
nodes:
  x: { out: [p], prompt: a }
  y: { in: [p], out: [q], prompt: b }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert len(guards) == 1


def test_long_straight_chain_does_not_recurse():
    # A recursive DFS would have killed the whole parse with RecursionError on this straight chain,
    # which
    # exceeds Python's default recursion limit (1000) — it blows up from node count alone, with no
    # cycle at all.
    n = 2000
    names = [f"n{i}" for i in range(n)]
    flow_line = " --> ".join(["input", *names, "output"])
    node_defs = "\n".join(f"  {name}: {{ prompt: p }}" for name in names)
    text = f"flow: |\n  {flow_line}\nnodes:\n{node_defs}\n"

    arch, _ = parse_arch(text)

    guards = [nd for nd in arch["nodes"] if nd["type"] == "loop.guard"]
    assert guards == []
    assert len(arch["nodes"]) == n + 2


def test_labelled_fanout_from_input_raises_with_line_number():
    """io.input has no way to pick a label itself — two labels is a trap that silently
    discards user intent (same class as the Task 3 diamond bug), so the parser
    rejects it with a line number."""
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input -->|a| x
  input -->|b| y
  x --> output
  y --> output
nodes:
  x: { in: [task], out: [m], prompt: p }
  y: { in: [task], out: [n], prompt: q }
""")
    message = str(exc.value)
    assert "input" in message
    assert "cannot branch" in message
    # The flow: block starts on line 3 of the document, and "input -->|a| x" is the next line.
    assert exc.value.line == 3


def test_single_labelled_edge_out_of_input_parses_fine():
    """One label is not a branch — where it goes is unambiguous, so there is no reason to reject."""
    arch, _ = parse_arch("""
flow: |
  input -->|start| x
  x --> output
nodes:
  x: { in: [task], out: [m], prompt: p }
""")
    assert [n["id"] for n in arch["nodes"]] == ["input", "x", "output"]


def test_looped_fixture_with_auto_inserted_guard_still_parses():
    """__guard_1 (auto-inserted) has two labels, loopBack/exit, but is of type loop.guard so
    it can branch — the LOOPED fixture must still parse cleanly."""
    arch, warnings = parse_arch(LOOPED)
    assert warnings == []
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert len(guards) == 1
    assert guards[0]["id"] == "__guard_1"


def test_explicit_loop_guard_with_loopback_exit_labels_parses_fine():
    """A guard the user pulled out directly with `{ run: loop.guard }` also carries the two
    loopBack/exit labels but is of type loop.guard, so it can branch — same shape as
    test_explicit_guard_is_left_alone, checked explicitly here from this file's branchable-type
    angle."""
    arch, _ = parse_arch("""
flow: |
  input --> solve --> review
  review -->|ok|    output
  review -->|retry| retry5
  retry5 -->|loopBack| solve
  retry5 -->|exit|     output
nodes:
  solve:   { in: [task], out: [answer], prompt: p }
  review:   { in: [answer], out: [verdict], prompt: q }
  retry5: { run: loop.guard, max: 5 }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert [g["id"] for g in guards] == ["retry5"]


def test_human_checkpoint_with_two_labelled_edges_parses_fine():
    """human.checkpoint can branch because the runtime (human approve/reject) decides the label.
    Sending reject to a separate terminal (output2) avoids a cycle (and thus guard insertion),
    so only the branchable-type validation is checked, in isolation."""
    arch, _ = parse_arch("""
flow: |
  input --> x --> approval
  approval -->|approve| output
  approval -->|reject|  output2
nodes:
  x: { in: [task], out: [draft], prompt: p }
  output2: { run: output }
  approval: { run: human.checkpoint }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["approval"]["type"] == "human.checkpoint"


def test_duplicate_branch_label_on_same_node_raises_with_line_number():
    """If a label is duplicated on the same node (both "ok"), the dict comprehension collapses
    them into one and the other edge becomes unreachable — the parser rejects it with the line
    number of the second occurrence."""
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input --> judge
  judge -->|ok| output
  judge -->|ok| other
nodes:
  judge: { in: [task], out: [verdict], prompt: p }
  other: { run: output }
""")
    message = str(exc.value)
    assert "judge" in message
    assert "ok" in message
    assert exc.value.line == 5


def test_distinct_branch_labels_still_parse_fine():
    """Two different labels is a normal branch — a guard test to prevent over-rejection."""
    arch, _ = parse_arch("""
flow: |
  input --> judge
  judge -->|ok| output
  judge -->|no| other
nodes:
  judge: { in: [task], out: [verdict], prompt: p }
  other: { run: output }
""")
    assert {n["id"] for n in arch["nodes"]} == {"input", "judge", "output", "other"}


def test_malformed_arrow_inside_flow_block_reports_correct_physical_line():
    """BLOCKING 2: the old code added the offset only to successful edges *after* calling
    parse_flow,
    so an ArchError thrown inside parse_flow (block-relative line number) leaked out
    uncorrected — it really goes wrong when flow: is not the document's first key. Passing
    line_offset to parse_flow up front gives the error path the same correction as the success
    path."""
    text = (
        "name: x\n"
        "model: google/gemini-3.1-flash-lite\n"
        "flow: |\n"
        "  input --> a\n"
        "  a --> b\n"
        "  this is not an edge\n"
        "  b --> output\n"
        "nodes:\n"
        "  a: { in: [task], out: [x], prompt: p }\n"
        "  b: { in: [x], out: [y], prompt: q }\n"
    )
    with pytest.raises(ArchError) as exc:
        parse_arch(text)
    assert exc.value.line == 6  # actual physical line of "  this is not an edge"
    assert "this is not an edge" in str(exc.value)


def test_inline_flow_scalar_malformed_line_reports_correct_physical_line():
    """Unlike a block scalar, a `flow: "..."` inline scalar has its content on the same physical
    line as flow: — if the offset calculation doesn't distinguish block from inline it is off by
    one."""
    text = 'name: x\nflow: "a --> b -->"\nnodes:\n  a: { out: [x], prompt: p }\n'
    with pytest.raises(ArchError) as exc:
        parse_arch(text)
    assert exc.value.line == 2  # same physical line as flow:


def test_yaml_syntax_error_raises_arch_error_with_line_and_pyyaml_message():
    """Does it swallow the YAMLError that yaml.safe_load itself throws (not a ValueError subclass)
    and re-wrap it as ArchError — for REST/WS to get a 400/error with a line number instead of a
    500,
    this must happen exactly once, inside parse_arch."""
    text = (
        "name: x\n"
        "flow: |\n"
        "  a --> b\n"
        "nodes:\n"
        "  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n"
    )
    with pytest.raises(ArchError) as exc:
        parse_arch(text)
    assert exc.value.line == 6  # actual file line (1-based) that PyYAML's problem_mark points to
    assert "expected ',' or '}'" in str(exc.value)


def test_yaml_syntax_error_line_number_is_not_double_corrected_when_flow_is_not_first_key():
    """Even when flow: is not the document's first key, problem_mark is already relative to the
    whole
    document, so _flow_line_offset must not be added — adding it makes the line number larger than
    the real one."""
    text = (
        "name: x\n"
        "model: google/gemini-3.1-flash-lite\n"
        "flow: |\n"
        "  a --> b\n"
        "nodes:\n"
        "  a: { out: [x], prompt: p\n"
        "  b: { in: [x], out: [y], prompt: q }\n"
    )
    with pytest.raises(ArchError) as exc:
        parse_arch(text)
    # physical line number as-is — the flow: offset (3) must not be added
    assert exc.value.line == 7


def test_valid_yaml_with_invalid_content_still_raises_domain_arch_error():
    """When the YAML syntax is fine but the content is wrong (reading a nonexistent out), the
    existing
    domain ArchError must come out as-is without going through the new YAMLError wrapper — the
    wrapper must not swallow or reclassify even such cases."""
    text = """
flow: |
  input --> a --> output
nodes:
  a: { in: [nope], out: [x], prompt: p }
"""
    with pytest.raises(ArchError) as exc:
        parse_arch(text)
    assert "nope" in str(exc.value)


def test_branch_node_with_unlabelled_edge_also_raises_with_line_number():
    """If a branch node (2+ labels) has even one more unlabelled outgoing edge, that edge is
    caught nowhere in compile.py and silently vanishes (BLOCKING 1) — the parser rejects it
    with that edge's line number."""
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input --> judge
  judge -->|ok| output
  judge -->|retry| fix
  judge --> logger
  fix --> judge
  logger --> output
nodes:
  judge: { in: [task], out: [verdict], prompt: p }
  fix: { in: [task], out: [verdict], prompt: q }
  logger: { in: [verdict], out: [logged], prompt: r }
""")
    message = str(exc.value)
    assert "judge" in message
    assert exc.value.line == 6  # actual line of "judge --> logger"
