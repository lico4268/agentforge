from typing import Literal

from config import ESCALATE_TAGS, MAX_RETRIES
from state import AgentState

ReviewBranch = Literal["accept", "refine", "clarify"]


def compute_review_branch(
    state: AgentState,
    *,
    max_retries: int = MAX_RETRIES,
    escalate_tags: set[str] | None = None,
    ignore_batch: bool = False,
) -> ReviewBranch:
    """순수 함수: ReviewDelta 내용 → accept/refine/clarify. 점수·confidence 없음.

    - must_pass unmet        → refine (재시도 소진 시 clarify)
    - unsure / misalignment / elicit 질문 → clarify
    - 전부 met (should_pass unmet 허용)   → accept
    - ESCALATE_TAGS 매칭 시 accept 금지 → clarify
    - batch_mode: clarify → accept 강등 (interrupt 불가 환경, ignore_batch로 원판정 조회)
    """
    escalate = ESCALATE_TAGS if escalate_tags is None else escalate_tags
    delta = state.get("review_delta")

    if delta is None:
        branch: ReviewBranch = "clarify"  # 리뷰 없이 통과 금지
    else:
        severity_by_id = {
            c.get("id"): c.get("severity", "must_pass") for c in (state.get("criteria") or [])
        }
        verdicts = delta.get("per_criterion") or []
        must_unmet = [
            v
            for v in verdicts
            if v.get("verdict") == "unmet"
            and severity_by_id.get(v.get("id"), "must_pass") == "must_pass"
        ]
        unsure = [v for v in verdicts if v.get("verdict") == "unsure"]

        if must_unmet:
            branch = "refine" if (state.get("retries") or 0) < max_retries else "clarify"
        elif unsure or delta.get("misalignments") or delta.get("elicit_questions"):
            branch = "clarify"
        else:
            branch = "accept"

    if branch == "accept" and set(state.get("task_tags") or []) & escalate:
        branch = "clarify"

    if branch == "clarify" and state.get("batch_mode") and not ignore_batch:
        branch = "accept"

    return branch


def make_route_review(wired: set[str] | None = None):
    """LangGraph conditional_edges용 sync 라우터.

    review 노드가 state["review_branch"]에 저장한 판정을 읽는다 — 노드에서
    retries가 증가한 뒤 재계산하면 판정이 어긋날 수 있어 재계산하지 않는다.
    wired가 주어지면 (캔버스 컴파일) 연결된 핸들로만 라우팅하고,
    미연결 브랜치는 보수적 순서(clarify > refine > accept)로 폴백한다.
    """

    def route_review(state: AgentState) -> str:
        branch = state.get("review_branch") or "clarify"
        if wired is None or branch in wired:
            return branch
        for fallback in ("clarify", "refine", "accept"):
            if fallback in wired:
                return fallback
        raise ValueError("review node has no outgoing edges")

    return route_review
