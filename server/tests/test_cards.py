"""cards 모듈 테스트 — 카드 파싱/로드."""

from pathlib import Path

from cards import CARDS_DIR, CardShell, JudgmentCard, _parse_card, load_cards, load_shells

SAMPLE_CARD = """---
card_id: math-001
version: 1
when_to_use: "Arithmetic word problems."
match_signals:
  - "how many"
  - "total"
pin: match_only
criteria:
  - id: final-number
    text: "Single numeric answer."
    severity: must_pass
    impl: llm
---
The user wants the correct final number above all else.
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_card_roundtrip(tmp_path: Path) -> None:
    path = _write(tmp_path / "math-001.md", SAMPLE_CARD)
    card = _parse_card(path)
    assert isinstance(card, JudgmentCard)
    assert card.card_id == "math-001"
    assert card.version == 1
    assert card.when_to_use == "Arithmetic word problems."
    assert card.match_signals == ["how many", "total"]
    assert card.pin == "match_only"
    assert card.representation.startswith("The user wants")
    assert len(card.criteria) == 1
    assert card.criteria[0]["id"] == "final-number"


def test_load_shells_sorted(tmp_path: Path) -> None:
    _write(tmp_path / "b-card.md", SAMPLE_CARD.replace("math-001", "b-card"))
    _write(tmp_path / "a-card.md", SAMPLE_CARD.replace("math-001", "a-card"))
    shells = load_shells(tmp_path)
    assert [s.card_id for s in shells] == ["a-card", "b-card"]
    for s in shells:
        assert isinstance(s, CardShell)
        assert not isinstance(s, JudgmentCard)


def test_load_cards_order_and_missing(tmp_path: Path) -> None:
    _write(tmp_path / "math-001.md", SAMPLE_CARD)
    _write(tmp_path / "writing-001.md", SAMPLE_CARD.replace("math-001", "writing-001"))
    cards = load_cards(["writing-001", "math-001", "nope-999"], tmp_path)
    assert [c.card_id for c in cards] == ["writing-001", "math-001"]


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_shells(tmp_path / "does-not-exist") == []
    assert load_cards(["x"], tmp_path / "does-not-exist") == []


def test_malformed_card_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "bad.md", "no frontmatter here")
    _write(tmp_path / "good.md", SAMPLE_CARD)
    shells = load_shells(tmp_path)
    assert [s.card_id for s in shells] == ["math-001"]


def test_real_seed_cards_parse() -> None:
    shells = load_shells(CARDS_DIR)
    ids = {s.card_id for s in shells}
    assert {"math-001", "math-002", "writing-001"}.issubset(ids)
