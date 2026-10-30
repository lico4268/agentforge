from datetime import UTC, datetime
from typing import Any, Protocol

from starlette.websockets import WebSocketState

from logging_config import logger
from workspace import persist_event

# ─── Event model (frontend-compatible flat shape) ──────────────────────────────


class ExecutionEvent:
    """
    1:1 with the frontend ExecutionEventSchema.
    serialize() returns the camelCase dict sent over the WebSocket.
    """

    __slots__ = (
        "event_type",
        "run_id",
        "node_id",
        "timestamp",
        "duration_ms",
        "input",
        "output",
        "token_usage",
        "policy_decision",
        "loop_runtime",
        "message",
        "error",
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
        loop_runtime: dict | None = None,
        message: str | None = None,
        error: dict | None = None,
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
        self.loop_runtime = loop_runtime
        self.message = message
        self.error = error

    def to_frontend(self) -> dict:
        """camelCase dict matching the frontend ExecutionEventSchema."""
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
        if self.loop_runtime is not None:
            d["loopRuntime"] = self.loop_runtime
        if self.message is not None:
            d["message"] = self.message
        if self.error is not None:
            d["error"] = self.error
        return d

    def model_dump(self) -> dict:
        """snake_case dict for the harness (internal). Keep fields symmetric with to_frontend()."""
        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "input": self.input,
            "output": self.output,
            "token_usage": self.token_usage,
            "policy_decision": self.policy_decision,
            "loop_runtime": self.loop_runtime,
            "message": self.message,
            "error": self.error,
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


def make_error_event(
    run_id: str,
    node_id: str,
    exc: BaseException,
    *,
    message: str | None = None,
) -> ExecutionEvent:
    """Standard node-failure event. event_type="error" + structured error field.

    The frontend eventReducer maps 'error' → status 'failed'.
    The error field has the shape {type, detail} and is shown as-is in LogPanel/Inspector.
    """
    return ExecutionEvent(
        event_type="error",
        run_id=run_id,
        node_id=node_id,
        message=message or str(exc),
        error={"type": type(exc).__name__, "detail": str(exc)},
    )


# ─── WebSocket emitter ─────────────────────────────────────────────────────────


async def safe_send_json(ws: Any, payload: dict) -> None:
    """Like ws.send_json, but silently ignored if called after the client has already disconnected.

    This commonly happens when the tab goes to the background or the network drops mid-run — it is
    not a bug in itself (especially when the client disconnects first during a long run), so we
    don't fill the server log with RuntimeErrors."""
    if getattr(ws, "client_state", None) != WebSocketState.CONNECTED:
        logger.debug("safe_send_json: websocket already closed, dropping message")
        return
    try:
        await ws.send_json(payload)
    except RuntimeError:
        logger.debug("safe_send_json: send raced with close, dropping message")


class WSEventEmitter:
    def __init__(self, websocket: Any, run_id: str, history: list[ExecutionEvent]):
        self.ws = websocket
        self.run_id = run_id
        self.history = history

    async def __call__(self, event: ExecutionEvent) -> None:
        self.history.append(event)
        persist_event(self.run_id, event)
        await safe_send_json(self.ws, {"kind": "event", "event": event.to_frontend()})


class FileEventEmitter:
    """Headless emitter: persists every event to the run's events.jsonl and collects them."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[ExecutionEvent] = []

    async def __call__(self, event: ExecutionEvent) -> None:
        self.events.append(event)
        persist_event(self.run_id, event)


# ─── List emitter (for harness) ────────────────────────────────────────────────


class ListEventEmitter:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def __call__(self, event: ExecutionEvent) -> None:
        self.events.append(event)
