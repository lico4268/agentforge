from datetime import UTC, datetime
from typing import Any, Protocol

# ─── Event model (frontend-compatible flat shape) ──────────────────────────────


class ExecutionEvent:
    """
    프론트 ExecutionEventSchema와 1:1 대응.
    serialize()가 WebSocket으로 나가는 camelCase dict를 반환한다.
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
        if self.loop_runtime is not None:
            d["loopRuntime"] = self.loop_runtime
        if self.message is not None:
            d["message"] = self.message
        if self.error is not None:
            d["error"] = self.error
        return d

    def model_dump(self) -> dict:
        """harness용 snake_case dict (내부 직렬화). to_frontend()와 필드 대칭 유지."""
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
    """노드 실패 표준 이벤트. event_type="error" + 구조화된 error 필드.

    프론트 eventReducer가 'error' → status 'failed'로 매핑한다.
    error 필드는 {type, detail} 형태로 LogPanel/Inspector에 그대로 표시된다.
    """
    return ExecutionEvent(
        event_type="error",
        run_id=run_id,
        node_id=node_id,
        message=message or str(exc),
        error={"type": type(exc).__name__, "detail": str(exc)},
    )


# ─── WebSocket emitter ─────────────────────────────────────────────────────────


class WSEventEmitter:
    def __init__(self, websocket: Any, run_id: str, history: list[ExecutionEvent]):
        self.ws = websocket
        self.run_id = run_id
        self.history = history

    async def __call__(self, event: ExecutionEvent) -> None:
        self.history.append(event)
        # node_end 이벤트의 output을 워크스페이스에 .md 파일로 영속화
        if event.event_type == "node_end" and event.output is not None:
            from workspace import write_node_output

            write_node_output(self.run_id, event.node_id, event.output)
        await self.ws.send_json({"kind": "event", "event": event.to_frontend()})


# ─── List emitter (for harness) ────────────────────────────────────────────────


class ListEventEmitter:
    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def __call__(self, event: ExecutionEvent) -> None:
        self.events.append(event)
