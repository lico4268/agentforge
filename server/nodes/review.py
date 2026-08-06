"""의도 정합성 리뷰 노드 — 결과물을 intent×criteria에 대조해 ReviewDelta(점수 없음)를 산출.

reasoning의 자기보고 confidence 대신, 독립 검증자 프롬프트가 원본 의도와
합격 기준에 결과물을 diff한다. 라우팅 판정(accept/refine/clarify)은 여기서
확정해 state["review_branch"]에 저장하고, 라우터는 그것을 읽기만 한다.
"""

from langchain_core.language_models import BaseChatModel

from config import ESCALATE_TAGS, MAX_RETRIES
from events import EventEmitter, make_event
from models import CallPolicy, ReviewDelta
from nodes.llm_step import run_llm_step
from nodes.policy import compute_review_branch
from state import AgentState

REVIEW_SYSTEM_PROMPT = """\
You are an independent reviewer. You did NOT produce the answer — judge it only by
comparing it against the original intent and the acceptance criteria. Never trust
any self-reported confidence, and never produce a score.

If no explicit Intent is given, the Task itself is the intent.
For each acceptance criterion (matched by its id), decide met / unmet / unsure and
quote exactly one piece of evidence from the answer. If there are no criteria,
leave per_criterion empty and judge intent alignment only.

Also report:
- misalignments: ways the answer diverges from the intent even where no criterion covers it
- elicit_questions: questions a human should answer to make the intent clearer (empty if clear)
- proposed_criteria: new checkable, one-sentence criteria worth adding for this kind of task
- reroute_hint: "planning" or "reasoning" if rework should restart there, else ""
"""


def _format_feedback(delta: dict, criteria: list[dict]) -> str:
    """refine 재작업용 피드백 — unmet delta만 전달 (부분 재작업)."""
    text_by_id = {c.get("id"): c.get("text", "") for c in criteria}
    lines = []
    for v in delta.get("per_criterion") or []:
        if v.get("verdict") == "unmet":
            cid = v.get("id")
            lines.append(f"- unmet [{cid}] {text_by_id.get(cid, '')}: {v.get('evidence', '')}")
    for m in delta.get("misalignments") or []:
        lines.append(f"- misalignment: {m}")
    return "\n".join(lines)


def make_review(
    model: BaseChatModel,
    emit: EventEmitter,
    run_id: str,
    node_id: str = "review",
    max_retries: int = MAX_RETRIES,
    escalate_tags: set[str] | None = None,
    seed_criteria: list[dict] | None = None,
    call_policy: CallPolicy | None = None,
    loop_policy_ids: list[str] | None = None,
):
    escalate = ESCALATE_TAGS if escalate_tags is None else escalate_tags
    policy_ids = loop_policy_ids or []

    async def review(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))

        # 노드 config 기준(seed)과 state 기준을 id로 병합 — state 쪽이 우선
        merged: dict[str, dict] = {c["id"]: c for c in (seed_criteria or [])}
        merged.update({c["id"]: c for c in (state.get("criteria") or [])})
        criteria = list(merged.values())

        probe: AgentState = {**state, "criteria": criteria}  # type: ignore[typeddict-item]
        usage: dict = {}
        delta = await run_llm_step(
            probe,
            node_id=node_id,
            system_prompt=REVIEW_SYSTEM_PROMPT,
            input_keys=[
                ("task", "Task"),
                ("intent", "Intent"),
                ("criteria", "Acceptance Criteria"),
                ("answer", "Answer"),
            ],
            output_model=ReviewDelta,
            model=model,
            emit=emit,
            run_id=run_id,
            call_policy=call_policy,
            usage_sink=usage,
        )

        probe = {**probe, "review_delta": delta}  # type: ignore[typeddict-item]
        branch = compute_review_branch(probe, max_retries=max_retries, escalate_tags=escalate)
        raw_branch = compute_review_branch(
            probe, max_retries=max_retries, escalate_tags=escalate, ignore_batch=True
        )

        updates: dict = {
            "review_delta": delta,
            "review_branch": branch,
            "criteria": criteria,
        }
        if branch == "refine":
            updates["feedback"] = _format_feedback(delta, criteria)
            updates["retries"] = (state.get("retries") or 0) + 1

        unmet = sum(1 for v in delta.get("per_criterion") or [] if v.get("verdict") == "unmet")

        if policy_ids:
            contribution: dict = {"progress_history": [float(unmet)]}
            if usage:
                contribution["total_tokens"] = usage.get("prompt", 0) + usage.get("completion", 0)
                contribution["total_cost_usd"] = usage.get("cost", 0.0)
            if updates.get("feedback") is not None:
                contribution["last_feedback"] = updates["feedback"]
            updates["loop_runtime"] = {pid: dict(contribution) for pid in policy_ids}

        reason = f"{unmet} unmet, {len(delta.get('misalignments') or [])} misaligned → {branch}"
        if raw_branch != branch:
            reason += f" (batch demoted from {raw_branch})"

        await emit(
            make_event(
                run_id,
                node_id,
                "node_end",
                output=delta,
                policy_decision={
                    "activated": branch != "accept",
                    "branch": branch,
                    "demoted": raw_branch != branch,
                    "reason": reason,
                },
            )
        )
        return updates

    return review
