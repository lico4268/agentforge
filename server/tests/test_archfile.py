import pytest

from archfile import ArchError, parse_flow


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
