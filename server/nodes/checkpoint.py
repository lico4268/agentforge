from langgraph.types import Command, interrupt

from events import EventEmitter, make_event
from state import AgentState


def make_human_checkpoint(emit: EventEmitter, run_id: str):
    async def human_checkpoint(state: AgentState) -> Command:
        payload = {
            "summary": state.get("answer") or "",
            "fields": {
                "task": state.get("task"),
                "answer": state.get("answer"),
                "confidence": state.get("confidence"),
                "verdict": state.get("verdict"),
            },
            "actions": ["approve", "revise", "reject"],
        }

        await emit(make_event(run_id, "human_checkpoint", "interrupt", **payload))

        # interrupt() 호출로 그래프 정지 — LangGraph가 값을 반환할 때까지 블록
        decision = interrupt(payload)

        action = decision.get("action", "approve")
        edits = decision.get("edits", {})
        reason = decision.get("reason", "")

        await emit(make_event(
            run_id, "human_checkpoint", "decision_record",
            decision=action,
            reason=reason,
            edits=edits,
            task_tags=state.get("task_tags", []),
            state_snapshot_ref=None,
        ))

        updates: dict = {}
        if edits:
            updates.update(edits)

        if action == "revise":
            updates["answer"] = edits.get("answer", state.get("answer"))
            return Command(goto="reasoning", update=updates)
        elif action == "reject":
            return Command(goto="output", update=updates)
        else:  # approve
            return Command(goto="output", update=updates)

    return human_checkpoint
