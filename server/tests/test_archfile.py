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
    edges = parse_flow("review -->|재시도| reasoning")
    assert edges[0] == {
        "source": "review",
        "target": "reasoning",
        "label": "재시도",
        "line": 1,
    }


def test_blank_lines_and_comments_ignored():
    edges = parse_flow("a --> b\n\n%% 주석\n  \nb --> c")
    assert len(edges) == 2
    assert edges[1]["line"] == 5


def test_unicode_node_names_allowed():
    edges = parse_flow("입력 --> 초안 --> 출력")
    assert [e["source"] for e in edges] == ["입력", "초안"]


def test_malformed_line_raises_with_line_number():
    with pytest.raises(ArchError) as exc:
        parse_flow("a --> b\nthis is not an edge")
    assert exc.value.line == 2
    assert "this is not an edge" in str(exc.value)


def test_label_only_on_first_hop_of_chain():
    edges = parse_flow("a -->|go| b --> c")
    assert edges[0]["label"] == "go"
    assert edges[1]["label"] == ""


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
name: 테스트 그래프
model: google/gemini-3.1-flash-lite

flow: |
  input --> 초안 --> 검토 --> output

nodes:
  초안:
    in:  [task]
    out: [draft]
    prompt: 빠르게 답을 내라.
  검토:
    in:  [task, draft]
    out: [answer]
    model: anthropic/claude-opus-5
    prompt: 허점을 짚어 고쳐라.
"""


def test_user_nodes_become_custom_node_type():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["초안"]["type"] == "custom.node"
    assert by_id["초안"]["config"]["systemPrompt"] == "빠르게 답을 내라."
    assert by_id["초안"]["config"]["outputs"] == [{"id": "draft", "label": "draft"}]
    assert by_id["초안"]["config"]["inputs"] == [{"id": "task", "label": "task"}]


def test_boundary_nodes_get_predefined_types():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["input"]["type"] == "io.input"
    assert by_id["output"]["type"] == "io.output"


def test_node_model_overrides_default():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["초안"]["config"]["modelSlots"][0]["model"] == "gemini-3.1-flash-lite"
    assert by_id["초안"]["config"]["modelSlots"][0]["provider"] == "google"
    assert by_id["검토"]["config"]["modelSlots"][0]["model"] == "claude-opus-5"
    assert by_id["검토"]["config"]["modelSlots"][0]["provider"] == "anthropic"


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
  b: { in: [나없음], out: [y], prompt: q }
""")
    assert "나없음" in str(exc.value)


def test_feedback_loop_input_with_no_upstream_producer_in_flow_order_parses():
    # reasoning은 flow 순서상 review보다 먼저 나오지만 review가 나중에 feedback을
    # 만든다 — 루프로 피드백이 돌아오는 정상 케이스(설계 §5.1)이지 오타가 아니다.
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
    # 삭제된 '?' 전처리는 원본 텍스트 전체를 건드렸었다 — 이제 전처리 자체가 없으니
    # in:/out: 문법을 흉내 낸 프롬프트 텍스트든 자연어 물음표든 손대지 않아야 한다.
    arch, _ = parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b:
    in:  [x]
    out: [y]
    prompt: "약속대로 in: [a?, b] out: [c?] 형태를 써도 되나? 정말 되나?"
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert (
        by_id["b"]["config"]["systemPrompt"]
        == "약속대로 in: [a?, b] out: [c?] 형태를 써도 되나? 정말 되나?"
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
  a --> 승인 --> output
nodes:
  a: { out: [x], prompt: p }
  승인: { run: human.checkpoint }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["승인"]["type"] == "human.checkpoint"


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
  input --> 풀이 --> 검토
  검토 -->|ok|    output
  검토 -->|retry| 풀이

nodes:
  풀이:  { in: [task, feedback], out: [answer], prompt: 풀어라 }
  검토:  { in: [task, answer],    out: [verdict, feedback], prompt: 검토하라 }
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
    # 검토 --retry--> __guard_1 로 바뀌었고 풀이로 직접 가지 않는다
    retry = [e for e in by_src["검토"] if e["sourceRole"] == "retry"][0]
    assert retry["target"] == "__guard_1"
    guard_targets = {e["sourceRole"]: e["target"] for e in by_src["__guard_1"]}
    assert guard_targets == {"loopBack": "풀이", "exit": "output"}


def test_explicit_guard_is_left_alone():
    arch, _ = parse_arch("""
flow: |
  input --> 풀이 --> 검토
  검토 -->|ok|    output
  검토 -->|retry| retry5
  retry5 -->|loopBack| 풀이
  retry5 -->|exit|     output
nodes:
  풀이:   { in: [task], out: [answer], prompt: p }
  검토:   { in: [answer], out: [verdict], prompt: q }
  retry5: { run: loop.guard, max: 5 }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert [g["id"] for g in guards] == ["retry5"]
    assert guards[0]["config"]["maxIterations"] == 5


def test_ambiguous_exit_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input --> 풀이 --> 검토
  검토 -->|a| out1
  검토 -->|b| out2
  검토 -->|retry| 풀이
nodes:
  풀이: { in: [task], out: [answer], prompt: p }
  검토: { in: [answer], out: [v], prompt: q }
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
    # a와 b가 각자 c로 모이는 순수 fan-in. flow 첫 등장 순서로는 (input, a, c, b, output)라
    # b --> c가 "뒤로 가는" 것처럼 보이지만, 실제로는 사이클이 전혀 없다.
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
    # input->output는 첫 DFS root에서 전부 방문되고 끝난다. x/y 사이클은 거기서 전혀
    # 도달되지 않는 별도 컴포넌트라, root를 nodes 순서대로 전부 순회하지 않으면 놓친다.
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
    # 재귀 DFS였다면 파이썬 기본 재귀 한도(1000)를 넘는 이 직선 체인에서
    # RecursionError로 파싱 전체가 죽었을 것 — 사이클이 전혀 없어도 노드 수만으로 터진다.
    n = 2000
    names = [f"n{i}" for i in range(n)]
    flow_line = " --> ".join(["input", *names, "output"])
    node_defs = "\n".join(f"  {name}: {{ prompt: p }}" for name in names)
    text = f"flow: |\n  {flow_line}\nnodes:\n{node_defs}\n"

    arch, _ = parse_arch(text)

    guards = [nd for nd in arch["nodes"] if nd["type"] == "loop.guard"]
    assert guards == []
    assert len(arch["nodes"]) == n + 2
