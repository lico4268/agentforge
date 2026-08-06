"""state.py — loop_runtime 병합 reducer 단위 테스트."""

from state import empty_loop_runtime, initial_state, merge_loop_runtime


def test_initial_state_has_empty_loop_runtime():
    state = initial_state("task")
    assert state["loop_runtime"] == {}


def test_merge_loop_runtime_sums_tokens_and_cost():
    existing = {"loop-1": {**empty_loop_runtime(), "total_tokens": 100, "total_cost_usd": 0.01}}
    new = {"loop-1": {"total_tokens": 50, "total_cost_usd": 0.02}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["total_tokens"] == 150
    assert round(merged["loop-1"]["total_cost_usd"], 4) == 0.03


def test_merge_loop_runtime_replaces_iteration_and_started_at():
    existing = {"loop-1": {**empty_loop_runtime(), "iteration": 1, "started_at": 10.0}}
    new = {"loop-1": {"iteration": 2, "started_at": 10.0}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["iteration"] == 2
    assert merged["loop-1"]["started_at"] == 10.0


def test_merge_loop_runtime_leaves_unset_fields_untouched():
    existing = {"loop-1": {**empty_loop_runtime(), "iteration": 3, "total_tokens": 200}}
    # 토큰만 기여하는 멤버 노드의 부분 업데이트 — iteration은 그대로 유지돼야 한다.
    new = {"loop-1": {"total_tokens": 10}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["iteration"] == 3
    assert merged["loop-1"]["total_tokens"] == 210


def test_merge_loop_runtime_appends_progress_history():
    existing = {"loop-1": {**empty_loop_runtime(), "progress_history": [3.0, 2.0]}}
    new = {"loop-1": {"progress_history": [1.0]}}

    merged = merge_loop_runtime(existing, new)

    assert merged["loop-1"]["progress_history"] == [3.0, 2.0, 1.0]


def test_merge_loop_runtime_initializes_unknown_policy():
    merged = merge_loop_runtime({}, {"loop-1": {"iteration": 1, "total_tokens": 5}})

    assert merged["loop-1"]["iteration"] == 1
    assert merged["loop-1"]["total_tokens"] == 5
    assert merged["loop-1"]["progress_history"] == []
