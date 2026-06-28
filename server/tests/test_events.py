"""ExecutionEvent / make_error_event 표준 실패 이벤트 검증."""
from events import make_error_event


def test_make_error_event_shape():
    exc = ValueError("bad output")
    ev = make_error_event("run-1", "reasoning", exc)

    assert ev.event_type == "error"
    assert ev.node_id == "reasoning"
    assert ev.error == {"type": "ValueError", "detail": "bad output"}
    assert ev.message == "bad output"


def test_make_error_event_custom_message():
    ev = make_error_event("run-1", "reasoning", RuntimeError("x"), message="복구 실패")
    assert ev.message == "복구 실패"
    assert ev.error["type"] == "RuntimeError"


def test_to_frontend_includes_error_camelcase():
    ev = make_error_event("run-1", "reasoning", KeyError("missing"))
    payload = ev.to_frontend()

    # 프론트 ExecutionEventSchema와 일치: eventType="error" + error 객체
    assert payload["eventType"] == "error"
    assert payload["error"]["type"] == "KeyError"
    # 실패 외 이벤트에는 error 키가 없어야 한다.
    from events import make_event

    ok = make_event("run-1", "reasoning", "node_start")
    assert "error" not in ok.to_frontend()
