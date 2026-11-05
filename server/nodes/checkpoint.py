from langgraph.types import Command, interrupt

from events import EventEmitter, make_event
from state import AgentState, read_state_value


def make_human_checkpoint(
    emit: EventEmitter,
    run_id: str,
    routes: dict[str, str],
    node_id: str,
    actions: list[str] | None = None,
    show_keys: list[str] | None = None,
):
    """show_keys: state keys the upstream nodes wrote — shown to the person as the question."""
    show_keys = show_keys or []

    async def human_checkpoint(state: AgentState) -> Command:
        shown = {k: read_state_value(state, k) for k in show_keys}
        parts = [f"{k}:\n{v}" if len(shown) > 1 else str(v) for k, v in shown.items() if v]
        payload = {
            "summary": "\n\n".join(parts),
            "fields": {"task": state.get("task"), **shown},
            "actions": actions or ["approve", "revise", "reject"],
        }

        await emit(make_event(run_id, node_id, "interrupt", output=payload))

        # Graph halts via the interrupt() call — blocks until LangGraph returns a value
        decision = interrupt(payload)

        action = decision.get("action", "approve")
        edits = decision.get("edits", {})
        reason = decision.get("reason", "")

        await emit(
            make_event(
                run_id,
                node_id,
                "decision_record",
                output={"decision": action, "reason": reason, "edits": edits},
            )
        )

        target = routes.get(action, routes.get("approve", "output"))
        return Command(goto=target, update=edits)

    return human_checkpoint
