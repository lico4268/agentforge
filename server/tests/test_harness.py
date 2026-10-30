"""Unit tests for harness.gsm8k_grader and run_dataset error handling — mostly pure logic."""

import pytest

from harness import Item, gsm8k_grader, run_dataset


@pytest.mark.parametrize(
    ("answer", "gold", "expected"),
    [
        ("The answer is 42", "42", True),  # last number matches
        ("Result 18", "#### 18", True),  # no noise numbers in gold
        ("Final answer: 7", "answer 7", True),
        ("The answer is 99", "100", False),  # mismatch
        ("3.5", "3.5", True),  # decimal
        ("", "42", False),  # empty answer
        (None, "42", False),  # None answer
        ("no number", "42", False),  # no number in answer
        ("72.0", "72", True),  # decimal notation difference — numeric comparison
        ("Answer: 1,200 dollars", "1200", True),  # thousands comma
        ("$18", "18.00", True),  # currency symbol + decimal gold
        ("-3", "-3.0", True),  # negative
    ],
)
def test_gsm8k_grader(answer, gold, expected):
    assert gsm8k_grader(answer, gold) is expected


def test_gsm8k_grader_uses_last_number():
    # With multiple numbers, grade by the last number.
    assert gsm8k_grader("First 10, then on recalculating 25", "25") is True
    assert gsm8k_grader("First 25, then on recalculating 10", "25") is False


class FakeGraph:
    """Fake graph that always raises — for verifying run_dataset error handling."""

    async def ainvoke(self, state, config):
        raise ValueError("boom")


def _fake_build_graph(emitter, run_id):
    return FakeGraph()


async def test_run_dataset_counts_errors():
    # 3 consecutive failures — below the threshold (5), so completes without RuntimeError
    items = [Item(question=f"q{i}", gold="1") for i in range(3)]
    report = await run_dataset(_fake_build_graph, items)
    assert report.error_rate == 1.0
    assert report.pass_at_1 == 0.0


async def test_run_dataset_aborts_on_consecutive_failures():
    # All 6 items raise — the consecutive-failure threshold is hit at the 5th, raising RuntimeError
    items = [Item(question=f"q{i}", gold="1") for i in range(6)]
    with pytest.raises(RuntimeError):
        await run_dataset(_fake_build_graph, items)
