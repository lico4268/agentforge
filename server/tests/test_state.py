"""state.py — loop_runtime 병합 reducer 단위 테스트."""

from state import (
    empty_loop_runtime,
    initial_state,
    merge_loop_runtime,
    merge_vars,
    read_state_value,
    write_state_value,
)


def test_initial_state_has_empty_loop_runtime():
    state = initial_state("task")
    assert state["loop_runtime"] == {}


def test_initial_state_has_empty_vars():
    state = initial_state("task")
    assert state["vars"] == {}


def test_merge_vars_shallow_merges_and_lets_new_keys_win():
    merged = merge_vars({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert merged == {"a": 1, "b": 3, "c": 4}


def test_read_state_value_reads_known_key_from_top_level():
    state = initial_state("hi")
    assert read_state_value(state, "task") == "hi"


def test_read_state_value_reads_unknown_key_from_vars():
    state = initial_state("hi")
    state["vars"] = {"myCustomField": 42}
    assert read_state_value(state, "myCustomField") == 42


def test_read_state_value_returns_none_for_unknown_key_missing_from_vars():
    state = initial_state("hi")
    assert read_state_value(state, "neverSet") is None


def test_write_state_value_writes_known_key_at_top_level():
    updates: dict = {}
    write_state_value(updates, "answer", "42")
    assert updates == {"answer": "42"}


def test_write_state_value_writes_unknown_key_into_vars():
    updates: dict = {}
    write_state_value(updates, "myCustomField", 42)
    assert updates == {"vars": {"myCustomField": 42}}


def test_write_state_value_accumulates_multiple_unknown_keys_into_one_vars_dict():
    updates: dict = {}
    write_state_value(updates, "a", 1)
    write_state_value(updates, "b", 2)
    assert updates == {"vars": {"a": 1, "b": 2}}


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
