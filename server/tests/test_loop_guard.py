"""nodes/loop_guard.py — unit tests for the pure guard evaluation function. No LangGraph needed."""

import time

from nodes.loop_guard import evaluate_loop_guard, next_runtime
from state import empty_loop_runtime


def _policy(**guard) -> dict:
    return {
        "id": "loop-1",
        "kind": "critiqueRevise",
        "feedbackEdgeIds": ["e1"],
        "memberNodeIds": [],
        "exitEdgeIds": ["e2"],
        "guard": guard,
        "onExhaustion": "exit",
    }


def test_no_guard_configured_always_continues():
    runtime = next_runtime(None)
    result = evaluate_loop_guard(_policy(), runtime)
    assert result == {"should_continue": True, "exit_reason": None}


def test_max_iterations_trips_when_exceeded():
    policy = _policy(maxIterations=2)
    runtime = {**empty_loop_runtime(), "iteration": 3}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "maxIterations"}


def test_max_iterations_allows_up_to_limit():
    policy = _policy(maxIterations=2)
    runtime = {**empty_loop_runtime(), "iteration": 2}
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_max_tokens_trips_when_exceeded():
    policy = _policy(maxTokens=1000)
    runtime = {**empty_loop_runtime(), "iteration": 1, "total_tokens": 1200}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_max_cost_trips_when_exceeded():
    policy = _policy(maxCostUsd=0.5)
    runtime = {**empty_loop_runtime(), "iteration": 1, "total_cost_usd": 0.6}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_max_duration_trips_when_exceeded():
    policy = _policy(maxDurationSec=1)
    runtime = {**empty_loop_runtime(), "iteration": 1, "started_at": time.time() - 5}
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "budget"}


def test_stuck_trips_when_progress_history_plateaus():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {
        **empty_loop_runtime(),
        "iteration": 3,
        "progress_history": [4.0, 4.0, 4.0],  # no improvement over 3 passes
    }
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "stuck"}


def test_stuck_trips_on_flat_plateau_with_omitted_threshold():
    """Complete stagnation (improvement==0) must be caught as stuck when threshold is omitted.
    With the threshold default of 0 and `improvement < threshold`, 0 < 0 == False would
    have missed this case — fixed to `<=` to prevent this regression."""
    policy = _policy(stuck={"window": 3})
    runtime = {
        **empty_loop_runtime(),
        "iteration": 3,
        "progress_history": [4.0, 4.0, 4.0],
    }
    result = evaluate_loop_guard(policy, runtime)
    assert result == {"should_continue": False, "exit_reason": "stuck"}


def test_stuck_does_not_trip_before_window_is_full():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {**empty_loop_runtime(), "iteration": 2, "progress_history": [4.0, 4.0]}
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_stuck_does_not_trip_when_improving():
    policy = _policy(stuck={"window": 3, "threshold": 1})
    runtime = {
        **empty_loop_runtime(),
        "iteration": 3,
        "progress_history": [4.0, 2.0, 0.0],  # improvement 4 >= threshold 1
    }
    result = evaluate_loop_guard(policy, runtime)
    assert result["should_continue"] is True


def test_next_runtime_increments_iteration_and_fixes_started_at():
    first = next_runtime(None)
    assert first["iteration"] == 1
    assert first["started_at"] > 0

    second = next_runtime(first)
    assert second["iteration"] == 2
    assert second["started_at"] == first["started_at"]  # first timestamp is pinned
