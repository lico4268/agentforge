"""compute_review_branch/make_route_review 단위 테스트 — 순수 함수, 외부 의존성 없음."""

import pytest

from nodes.policy import compute_review_branch, make_route_review

ESCALATE = {"high-stakes"}


def build_state(**overrides) -> dict:
    state = {
        "task_tags": [],
        "batch_mode": False,
        "retries": 0,
        "criteria": [],
        "review_delta": None,
        "review_branch": None,
    }
    state.update(overrides)
    return state


def build_delta(per_criterion=None, misalignments=None, elicit_questions=None) -> dict:
    return {
        "per_criterion": per_criterion or [],
        "misalignments": misalignments or [],
        "elicit_questions": elicit_questions or [],
        "proposed_criteria": [],
        "reroute_hint": "",
    }


def branch_of(state, **kwargs) -> str:
    return compute_review_branch(state, max_retries=2, escalate_tags=ESCALATE, **kwargs)


def test_no_delta_is_clarify():
    # 리뷰 없이 통과 금지
    assert branch_of(build_state(review_delta=None)) == "clarify"


def test_all_met_is_accept():
    state = build_state(
        criteria=[{"id": "c1", "severity": "must_pass"}],
        review_delta=build_delta([{"id": "c1", "verdict": "met", "evidence": "ok"}]),
    )
    assert branch_of(state) == "accept"


def test_must_pass_unmet_refines_within_retries():
    state = build_state(
        criteria=[{"id": "c1", "severity": "must_pass"}],
        review_delta=build_delta([{"id": "c1", "verdict": "unmet", "evidence": "x"}]),
        retries=1,
    )
    assert branch_of(state) == "refine"


def test_must_pass_unmet_clarifies_after_retries_exhausted():
    state = build_state(
        criteria=[{"id": "c1", "severity": "must_pass"}],
        review_delta=build_delta([{"id": "c1", "verdict": "unmet", "evidence": "x"}]),
        retries=2,
    )
    assert branch_of(state) == "clarify"


def test_unknown_criterion_id_defaults_to_must_pass():
    state = build_state(
        review_delta=build_delta([{"id": "ghost", "verdict": "unmet", "evidence": "x"}]),
    )
    assert branch_of(state) == "refine"


def test_should_pass_unmet_alone_still_accepts():
    state = build_state(
        criteria=[{"id": "c1", "severity": "should_pass"}],
        review_delta=build_delta([{"id": "c1", "verdict": "unmet", "evidence": "x"}]),
    )
    assert branch_of(state) == "accept"


@pytest.mark.parametrize(
    "delta",
    [
        build_delta([{"id": "c1", "verdict": "unsure", "evidence": "?"}]),
        build_delta(misalignments=["단위 누락"]),
        build_delta(elicit_questions=["단위는 원인가요?"]),
    ],
)
def test_unsure_or_misalignment_or_elicit_is_clarify(delta):
    state = build_state(
        criteria=[{"id": "c1", "severity": "must_pass"}],
        review_delta=delta,
    )
    assert branch_of(state) == "clarify"


def test_escalate_tag_blocks_accept():
    state = build_state(task_tags=["high-stakes"], review_delta=build_delta())
    assert branch_of(state) == "clarify"


def test_escalate_tag_does_not_block_refine():
    state = build_state(
        task_tags=["high-stakes"],
        review_delta=build_delta([{"id": "c1", "verdict": "unmet", "evidence": "x"}]),
    )
    assert branch_of(state) == "refine"


def test_batch_mode_demotes_clarify_to_accept():
    state = build_state(batch_mode=True, review_delta=build_delta(misalignments=["m"]))
    assert branch_of(state) == "accept"
    assert branch_of(state, ignore_batch=True) == "clarify"


def test_route_reads_stored_branch():
    route = make_route_review()
    assert route(build_state(review_branch="refine")) == "refine"
    # 저장된 판정이 없으면 보수적으로 clarify
    assert route(build_state(review_branch=None)) == "clarify"


def test_route_respects_wired_handles():
    route = make_route_review(wired={"accept", "clarify"})
    assert route(build_state(review_branch="clarify")) == "clarify"


def test_route_falls_back_conservatively_when_unwired():
    # refine 미배선 → clarify > refine > accept 순 폴백
    route = make_route_review(wired={"accept", "clarify"})
    assert route(build_state(review_branch="refine")) == "clarify"
    route = make_route_review(wired={"accept"})
    assert route(build_state(review_branch="refine")) == "accept"


def test_route_raises_without_edges():
    route = make_route_review(wired=set())
    with pytest.raises(ValueError):
        route(build_state(review_branch="accept"))
