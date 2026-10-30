"""Verify ExecutionEvent / make_error_event standard failure events."""

from events import make_error_event, make_event


def test_make_error_event_shape():
    exc = ValueError("bad output")
    ev = make_error_event("run-1", "reasoning", exc)

    assert ev.event_type == "error"
    assert ev.node_id == "reasoning"
    assert ev.error == {"type": "ValueError", "detail": "bad output"}
    assert ev.message == "bad output"


def test_make_error_event_custom_message():
    ev = make_error_event("run-1", "reasoning", RuntimeError("x"), message="recovery failed")
    assert ev.message == "recovery failed"
    assert ev.error["type"] == "RuntimeError"


def test_to_frontend_includes_error_camelcase():
    ev = make_error_event("run-1", "reasoning", KeyError("missing"))
    payload = ev.to_frontend()

    # Matches the frontend ExecutionEventSchema: eventType="error" + error object
    assert payload["eventType"] == "error"
    assert payload["error"]["type"] == "KeyError"
    # Non-failure events must not have an error key.
    ok = make_event("run-1", "reasoning", "node_start")
    assert "error" not in ok.to_frontend()


def test_to_frontend_includes_loop_runtime_camelcase():
    ev = make_event(
        "run-1",
        "loop_guard",
        "node_end",
        loop_runtime={"loopNodeId": "loop_guard", "iteration": 2, "exitReason": "maxIterations"},
    )
    payload = ev.to_frontend()

    assert payload["loopRuntime"] == {
        "loopNodeId": "loop_guard",
        "iteration": 2,
        "exitReason": "maxIterations",
    }
    # The guard event's nodeId is the loopNodeId — the frontend consumes it like regular nodes.
    assert payload["nodeId"] == payload["loopRuntime"]["loopNodeId"]


def test_to_frontend_omits_loop_runtime_when_absent():
    ev = make_event("run-1", "reasoning", "node_start")
    assert "loopRuntime" not in ev.to_frontend()
