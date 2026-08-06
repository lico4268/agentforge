"""LoopPolicy.guard 5축(iteration/token/cost/duration/stuck) 순수 평가 로직.

LangGraph·이벤트 방출과 완전히 분리돼 있다 — graphs/compile.py의
_make_loop_guard_node가 이 모듈을 호출해 실제 그래프 라우팅에 반영한다.
새 가드 축이 추가되면 여기와 state.LoopRuntimeState만 넓히면 되고, 컴파일러
배선(어떤 노드 타입이 가드를 받는지)은 다시 건드릴 필요가 없다.
"""

import time
from typing import Literal, TypedDict

from state import LoopRuntimeState, empty_loop_runtime

ExitReason = Literal["success", "maxIterations", "budget", "stuck", "escalated", "failed"]


class GuardResult(TypedDict):
    should_continue: bool
    exit_reason: ExitReason | None


def evaluate_loop_guard(policy: dict, runtime: LoopRuntimeState) -> GuardResult:
    """policy["guard"]의 축을 순서대로 확인한다. 하나라도 트립되면 즉시 종료 판정.

    runtime은 이번 패스분(iteration 증가분 포함)까지 반영된 값을 넘겨야 한다
    (next_runtime()이 만든 값). 이 함수 자체는 iteration을 증가시키지 않는다.
    """
    guard = policy.get("guard") or {}

    max_iterations = guard.get("maxIterations")
    if max_iterations is not None and runtime["iteration"] > max_iterations:
        return {"should_continue": False, "exit_reason": "maxIterations"}

    max_tokens = guard.get("maxTokens")
    if max_tokens is not None and runtime["total_tokens"] > max_tokens:
        return {"should_continue": False, "exit_reason": "budget"}

    max_cost = guard.get("maxCostUsd")
    if max_cost is not None and runtime["total_cost_usd"] > max_cost:
        return {"should_continue": False, "exit_reason": "budget"}

    max_duration = guard.get("maxDurationSec")
    if max_duration is not None and (time.time() - runtime["started_at"]) > max_duration:
        return {"should_continue": False, "exit_reason": "budget"}

    stuck_cfg = guard.get("stuck")
    if stuck_cfg is not None and _is_stuck(runtime["progress_history"], stuck_cfg):
        return {"should_continue": False, "exit_reason": "stuck"}

    return {"should_continue": True, "exit_reason": None}


def _is_stuck(progress_history: list[float], stuck_cfg: dict) -> bool:
    """window 구간의 진행 신호(낮을수록 좋음, 예: unmet 기준 개수) 개선폭이
    threshold 미만이면 stuck. 기록이 window보다 적으면 아직 판단하지 않는다.
    """
    window = int(stuck_cfg.get("window", 0))
    threshold = float(stuck_cfg.get("threshold", 0))
    if window <= 0 or len(progress_history) < window:
        return False
    recent = progress_history[-window:]
    improvement = recent[0] - recent[-1]
    return improvement < threshold


def next_runtime(prior: LoopRuntimeState | None) -> LoopRuntimeState:
    """가드 진입 시 호출 — iteration을 1 증가시키고 started_at을 최초 1회만 고정한다."""
    base = prior or empty_loop_runtime()
    return {
        "iteration": base["iteration"] + 1,
        "total_tokens": base["total_tokens"],
        "total_cost_usd": base["total_cost_usd"],
        "started_at": base["started_at"] or time.time(),
        "last_feedback": base["last_feedback"],
        "progress_history": base["progress_history"],
    }
