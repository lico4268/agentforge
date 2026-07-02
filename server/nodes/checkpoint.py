from langgraph.types import Command, interrupt

from events import EventEmitter, make_event
from state import AgentState


def make_human_checkpoint(
    emit: EventEmitter,
    run_id: str,
    routes: dict[str, str] | None = None,
    node_id: str = "human_checkpoint",
):
    routes = routes or {"approve": "output", "revise": "reasoning", "reject": "output"}

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

        await emit(make_event(run_id, node_id, "interrupt", output=payload))

        # interrupt() 호출로 그래프 정지 — LangGraph가 값을 반환할 때까지 블록
        decision = interrupt(payload)

        action = decision.get("action", "approve")
        edits = decision.get("edits", {})
        reason = decision.get("reason", "")

        await emit(make_event(
            run_id, node_id, "decision_record",
            output={
                "decision": action,
                "reason": reason,
                "edits": edits,
                "task_tags": state.get("task_tags", []),
            },
        ))

        updates: dict = {}
        if edits:
            updates.update(edits)

        if action == "revise":
            updates["answer"] = edits.get("answer", state.get("answer"))

        target = routes.get(action, routes.get("approve", "output"))
        return Command(goto=target, update=updates)

    return human_checkpoint
