"""harness.gsm8k_grader 단위 테스트 — 순수 함수, 외부 의존성 없음."""

import pytest

from harness import gsm8k_grader


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
    ],
)
def test_gsm8k_grader(answer, gold, expected):
    assert gsm8k_grader(answer, gold) is expected


def test_gsm8k_grader_uses_last_number():
    # 여러 숫자가 있으면 마지막 숫자로 채점한다.
    assert gsm8k_grader("처음엔 10, 다시 계산하니 25", "25") is True
    assert gsm8k_grader("처음엔 25, 다시 계산하니 10", "25") is False
