"""classify 노드 테스트 — 카드 매칭/criteria 주입/intent 폴백/폴백 경로. LLM은 목(AGENTS.md §6)."""

from pathlib import Path
from typing import Any

import pytest

from events import ListEventEmitter
from models import ClassifyOut
from nodes.classify import make_classify
from state import AgentState, initial_state

CARD_MATH = """---
card_id: math-001
version: 1
when_to_use: "Arithmetic word problems."
match_signals:
  - "how many"
pin: match_only
criteria:
  - id: final-number
    text: "Single numeric answer."
    severity: must_pass
    impl: llm
---
The user wants the correct final number above all else.
"""

CARD_ALWAYS = """---
card_id: always-001
version: 1
when_to_use: "Universal card."
match_signals: []
pin: always
criteria:
  - id: universal
    text: "Always applied."
    severity: must_pass
    impl: llm
---
Universal guidance.
"""


def _write_cards(cards_dir: Path, items: list[tuple[str, str]]) -> None:
    for name, content in items:
        (cards_dir / name).write_text(content, encoding="utf-8")


def _install_fake_llm(
    monkeypatch: pytest.MonkeyPatch, out: ClassifyOut, counter: list[int]
) -> None:
    async def fake_run_llm_step(*args: Any, **kwargs: Any) -> dict:
        counter[0] += 1
        return out.model_dump()

    monkeypatch.setattr("nodes.classify.run_llm_step", fake_run_llm_step)


def _make_state(**overrides: Any) -> AgentState:
    base = initial_state(task="A shop sold 12 apples and 8 oranges. How many fruits total?")
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


async def test_no_cards_skips_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    counter = [0]
    _install_fake_llm(monkeypatch, ClassifyOut(card_ids=["math-001"]), counter)
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)

    result = await classify(_make_state())
    assert result == {"matched_cards": []}
    assert counter[0] == 0


async def test_match_injects_namespaced_criteria(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cards(tmp_path, [("math-001.md", CARD_MATH)])
    counter = [0]
    _install_fake_llm(monkeypatch, ClassifyOut(card_ids=["math-001"]), counter)
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)

    result = await classify(_make_state())
    assert result["matched_cards"] == ["math-001"]
    ids = [c["id"] for c in result["criteria"]]
    assert "math-001:final-number" in ids
    assert counter[0] == 1


async def test_intent_fallback_only_when_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cards(tmp_path, [("math-001.md", CARD_MATH)])
    counter = [0]
    _install_fake_llm(monkeypatch, ClassifyOut(card_ids=["math-001"]), counter)

    # intent 없음 → representation이 intent로 폴백
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)
    result = await classify(_make_state(intent=None))
    assert "intent" in result
    assert "correct final number" in result["intent"]

    # intent 있음 → updates에 intent 키 없음
    emit2 = ListEventEmitter()
    classify2 = make_classify(model=None, emit=emit2, run_id="r1", cards_dir=tmp_path)
    result2 = await classify2(_make_state(intent="already set"))
    assert "intent" not in result2


async def test_pin_always_included(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cards(tmp_path, [("math-001.md", CARD_MATH), ("always-001.md", CARD_ALWAYS)])
    counter = [0]
    _install_fake_llm(monkeypatch, ClassifyOut(card_ids=[]), counter)
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)

    result = await classify(_make_state())
    assert "always-001" in result["matched_cards"]


async def test_state_criteria_win_on_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cards(tmp_path, [("math-001.md", CARD_MATH)])
    counter = [0]
    _install_fake_llm(monkeypatch, ClassifyOut(card_ids=["math-001"]), counter)
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)

    state = _make_state(
        criteria=[
            {
                "id": "math-001:final-number",
                "text": "STATE WINS",
                "severity": "must_pass",
                "impl": "llm",
            }
        ]
    )
    result = await classify(state)
    by_id = {c["id"]: c for c in result["criteria"]}
    assert by_id["math-001:final-number"]["text"] == "STATE WINS"


async def test_llm_failure_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cards(tmp_path, [("math-001.md", CARD_MATH)])

    async def raising(*args: Any, **kwargs: Any) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("nodes.classify.run_llm_step", raising)
    emit = ListEventEmitter()
    classify = make_classify(model=None, emit=emit, run_id="r1", cards_dir=tmp_path)

    result = await classify(_make_state())
    assert result == {"matched_cards": []}
    kinds = {(e.node_id, e.event_type) for e in emit.events}
    assert ("classify", "node_end") in kinds
