from datetime import UTC, datetime
from typing import Any, Protocol

# ─── Event model (frontend-compatible flat shape) ──────────────────────────────

class ExecutionEvent:
    """
    프론트 ExecutionEventSchema와 1:1 대응.
    serialize()가 WebSocket으로 나가는 camelCase dict를 반환한다.
    """
    __slots__ = (
        "event_type", "run_id", "node_id", "timestamp",
        "duration_ms", "input", "output", "token_usage",
        "policy_decision", "message",
    )

    def __init__(
        self,
        event_type: str,
        run_id: str,
        node_id: str,
        *,
        duration_ms: int | None = None,
        input: Any = None,
        output: Any = None,
        token_usage: dict | None = None,
        policy_decision: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.event_type = event_type
        self.run_id = run_id
        self.node_id = node_id
        self.timestamp = datetime.now(UTC).isoformat()
        self.duration_ms = duration_ms
        self.input = input
        self.output = output
        self.token_usage = token_usage
        self.policy_decision = policy_decision
        self.message = message

    def to_frontend(self) -> dict:
        """프론트 ExecutionEventSchema와 일치하는 camelCase dict."""
        d: dict[str, Any] = {
            "eventType": self.event_type,
            "runId": self.run_id,
            "nodeId": self.node_id,
            "timestamp": self.timestamp,
        }
        if self.duration_ms is not None:
            d["durationMs"] = self.duration_ms
        if self.input is not None:
            d["input"] = self.input
        if self.output is not None:
            d["output"] = self.output
        if self.token_usage is not None:
            d["tokenUsage"] = self.token_usage
        if self.policy_decision is not None:
            d["policyDecision"] = self.policy_decision
        if self.message is not None:
            d["message"] = self.message
        return d

    def model_dump(self) -> dict:
        """harness용 snake_case dict (내부 직렬화)."""
        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "policy_decision": self.policy_decision,
            "message": self.message,
        }


class EventEmitter(Protocol):
    async def __call__(self, event: ExecutionEvent) -> None: ...


def make_event(
    run_id: str,
    node_id: str,
    event_type: str,
    **kwargs: Any,
) -> ExecutionEvent:
    return ExecutionEvent(event_type=event_type, run_id=run_id, node_id=node_id, **kwargs)


# ─── WebSocket emitter ─────────────────────────────────────────────────────────

class WSEventEmitter:
    def __init__(self, websocket: Any, run_id: str, history: list[ExecutionEvent]):
        self.ws = websocket
        self.run_id = run_id
        self.history = history

    async def __call__(self, event: ExecutionEvent) -> None:
        self.history.append(event)
        await self.ws.send_json({"kind": "event", "event": event.to_frontend()})


# ─── List emitter (for harness) ────────────────────────────────────────────────

class ListEventEmitter:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def __call__(self, event: ExecutionEvent) -> None:
        self.events.append(event)
