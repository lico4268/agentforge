"""harness.gsm8k_grader 및 run_dataset 에러 처리 단위 테스트 — 순수 로직 위주."""

import pytest

from harness import Item, gsm8k_grader, run_dataset


@pytest.mark.parametrize(
    ("answer", "gold", "expected"),
    [
        ("정답은 42입니다", "42", True),  # 마지막 숫자 일치
        ("계산 결과 18", "#### 18", True),  # gold에 잡음 숫자 없음
        ("최종 답: 7", "정답 7", True),
        ("답은 99", "100", False),  # 불일치
        ("3.5", "3.5", True),  # 소수
        ("", "42", False),  # 빈 answer
        (None, "42", False),  # None answer
        ("숫자 없음", "42", False),  # answer에 숫자 없음
        ("72.0", "72", True),  # 소수 표기 차이 — 수치 비교
        ("정답: 1,200원", "1200", True),  # 천단위 콤마
        ("$18", "18.00", True),  # 통화 기호 + 소수 gold
        ("-3", "-3.0", True),  # 음수
    ],
)
def test_gsm8k_grader(answer, gold, expected):
    assert gsm8k_grader(answer, gold) is expected


def test_gsm8k_grader_uses_last_number():
    # 여러 숫자가 있으면 마지막 숫자로 채점한다.
    assert gsm8k_grader("처음엔 10, 다시 계산하니 25", "25") is True
    assert gsm8k_grader("처음엔 25, 다시 계산하니 10", "25") is False


class FakeGraph:
    """항상 예외를 던지는 가짜 그래프 — run_dataset 에러 처리 검증용."""

    async def ainvoke(self, state, config):
        raise ValueError("boom")


def _fake_build_graph(emitter, run_id):
    return FakeGraph()


async def test_run_dataset_counts_errors():
    # 연속 3문항 실패 — 임계(5) 미만이므로 RuntimeError 없이 완료
    items = [Item(question=f"q{i}", gold="1") for i in range(3)]
    report = await run_dataset(_fake_build_graph, items)
    assert report.error_rate == 1.0
    assert report.pass_at_1 == 0.0


async def test_run_dataset_aborts_on_consecutive_failures():
    # 6문항 전부 예외 — 5번째에서 연속 실패 임계 도달하여 RuntimeError
    items = [Item(question=f"q{i}", gold="1") for i in range(6)]
    with pytest.raises(RuntimeError):
        await run_dataset(_fake_build_graph, items)
