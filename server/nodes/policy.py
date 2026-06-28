from typing import Literal

from config import AUTO_THRESHOLD, ESCALATE_TAGS, MAX_RETRIES, PASS_THRESHOLD
from state import AgentState


def compute_branch(state: AgentState) -> Literal["pass", "auto", "human"]:
    """순수 함수: state → 라우팅 브랜치. emit 없음."""
    c = state.get("confidence") or 0.0
    tags = set(state.get("task_tags") or [])

    if tags & ESCALATE_TAGS:
        branch: Literal["pass", "auto", "human"] = "human"
    elif c >= PASS_THRESHOLD:
        branch = "pass"
    elif c >= AUTO_THRESHOLD:
        branch = "auto"
    else:
        branch = "human"

    # batch_mode: human → auto 강등
    if branch == "human" and state.get("batch_mode"):
        branch = "auto"

    return branch


def make_route_review():
    """LangGraph conditional_edges용 sync 라우터. emit 없이 순수 라우팅만."""
    def route_review(state: AgentState) -> Literal["pass", "auto", "human"]:
        return compute_branch(state)
    return route_review


def make_route_verify():
    def route_verify(state: AgentState) -> Literal["output", "retry"]:
        verdict = state.get("verdict") or {}
        if verdict.get("passed"):
            return "output"
        if state.get("retries", 0) < MAX_RETRIES:
            return "retry"
        return "output"
    return route_verify
