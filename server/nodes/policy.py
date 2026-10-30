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
    """Pure function: ReviewDelta content → accept/refine/clarify. No score/confidence.

    - must_pass unmet        → refine (clarify once retries are exhausted)
    - unsure / misalignment / elicit question → clarify
    - all met (should_pass unmet allowed)   → accept
    - accept forbidden when ESCALATE_TAGS match → clarify
    - batch_mode: demote clarify → accept (no-interrupt envs; ignore_batch gives the raw verdict)
    """
    escalate = ESCALATE_TAGS if escalate_tags is None else escalate_tags
    delta = state.get("review_delta")

    if delta is None:
        branch: ReviewBranch = "clarify"  # no passing without review
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
    """Sync router for LangGraph conditional_edges.

    Reads the verdict the review node stored in state["review_branch"] — recomputing after
    retries is incremented in the node could make the verdict inconsistent, so we don't recompute.
    If wired is given (canvas compile), route only to connected handles,
    and fall back for unconnected branches in a conservative order (clarify > refine > accept).
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
