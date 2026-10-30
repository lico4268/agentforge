"""Pure evaluation logic for the 5 LoopPolicy.guard axes (iteration/token/cost/duration/stuck).

Fully decoupled from LangGraph and event emission — _make_loop_guard_node in graphs/compile.py
calls this module and applies the result to actual graph routing.
When a new guard axis is added, only this module and state.LoopRuntimeState need widening; the
compiler wiring (which node types receive a guard) doesn't need to be touched again.
"""

import time
from typing import Literal, TypedDict

from state import LoopRuntimeState, empty_loop_runtime

ExitReason = Literal["success", "maxIterations", "budget", "stuck", "escalated", "failed"]


class GuardResult(TypedDict):
    should_continue: bool
    exit_reason: ExitReason | None


def evaluate_loop_guard(policy: dict, runtime: LoopRuntimeState) -> GuardResult:
    """Check the axes in policy["guard"] in order. If any trips, the verdict is to stop immediately.

    runtime must be passed with this pass's values already reflected (incl. the iteration increment)
    (the value built by next_runtime()). This function itself does not increment iteration.
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
    """Stuck if the improvement in the progress signal over the window (lower is better, e.g. unmet
    criteria count) is below threshold. Not judged yet if there are fewer records than the window.
    """
    window = int(stuck_cfg.get("window", 0))
    threshold = float(stuck_cfg.get("threshold", 0))
    if window <= 0 or len(progress_history) < window:
        return False
    recent = progress_history[-window:]
    improvement = recent[0] - recent[-1]
    return improvement <= threshold


def next_runtime(prior: LoopRuntimeState | None) -> LoopRuntimeState:
    """Called on guard entry — increments iteration by 1 and pins started_at only the first time."""
    base = prior or empty_loop_runtime()
    return {
        "iteration": base["iteration"] + 1,
        "total_tokens": base["total_tokens"],
        "total_cost_usd": base["total_cost_usd"],
        "started_at": base["started_at"] or time.time(),
        "last_feedback": base["last_feedback"],
        "progress_history": base["progress_history"],
    }
