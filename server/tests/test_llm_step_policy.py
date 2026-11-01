"""Unit tests for run_llm_step call policy — retry / timeout / fallback.

Controls ainvoke behavior with a fake model (AGENTS.md §6). No real LLM API calls.
"""

import asyncio

import pytest
from pydantic import BaseModel

from events import ListEventEmitter
from models import CallPolicy, ModelSettings
from nodes import llm_step as llm_mod
from nodes.llm_step import run_llm_step


class Out(BaseModel):
    answer: str = "ok"


class FakeStructured:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        res = self.behavior(self.calls, messages)
        if asyncio.iscoroutine(res):
            res = await res
        return res


class FakeModel:
    def __init__(self, behavior, name="fake-model"):
        self.behavior = behavior
        self.model = name

    def with_structured_output(self, output_model):
        return FakeStructured(self.behavior)


async def _noop_sleep(*a, **kw):
    return None


async def test_retry_then_success(monkeypatch):
    """If it fails once and succeeds on retry, return the result and log the retry."""
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    def behavior(calls, messages):
        if calls == 1:
            raise RuntimeError("transient")
        return Out()

    model = FakeModel(behavior)
    emit = ListEventEmitter()
    result = await run_llm_step(
        {},
        node_id="n",
        system_prompt="s",
        input_keys=[],
        output_model=Out,
        model=model,
        emit=emit,
        run_id="r",
        call_policy=CallPolicy(retry_count=2, timeout_seconds=10),
    )
    assert result == {"answer": "ok"}
    logs = [e for e in emit.events if e.event_type == "log" and e.message]
    assert any("retry" in e.message for e in logs)
    assert not any(e.event_type == "error" for e in emit.events)


async def test_retry_exhausted_emits_error(monkeypatch):
    """After all retries are exhausted, emit an error event + re-raise the last exception."""
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    def behavior(calls, messages):
        raise RuntimeError("always fails")

    model = FakeModel(behavior)
    emit = ListEventEmitter()
    with pytest.raises(RuntimeError, match="always fails"):
        await run_llm_step(
            {},
            node_id="n",
            system_prompt="s",
            input_keys=[],
            output_model=Out,
            model=model,
            emit=emit,
            run_id="r",
            call_policy=CallPolicy(retry_count=1, timeout_seconds=10),
        )
    assert any(e.event_type == "error" and e.node_id == "n" for e in emit.events)


async def test_real_timeout_triggers_failure():
    """If ainvoke exceeds the timeout, wait_for raises TimeoutError → fails at once (no retries)."""
    # retry_count=0 → no backoff sleep. asyncio.sleep is not patched, so a real delay occurs.

    async def behavior(calls, messages):
        await asyncio.sleep(0.3)  # real delay — wait_for cancels at timeout (0.05)
        return Out()

    model = FakeModel(behavior)
    emit = ListEventEmitter()
    with pytest.raises(asyncio.TimeoutError):
        await run_llm_step(
            {},
            node_id="n",
            system_prompt="s",
            input_keys=[],
            output_model=Out,
            model=model,
            emit=emit,
            run_id="r",
            call_policy=CallPolicy(retry_count=0, timeout_seconds=0.05),
        )
    assert any(e.event_type == "error" for e in emit.events)


async def test_fallback_success_after_primary_failure(monkeypatch):
    """If the fallback succeeds first try after primary retries are exhausted, return the result."""
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    def primary_behavior(calls, messages):
        raise RuntimeError("primary down")

    def fallback_behavior(calls, messages):
        return Out(answer="fb")

    primary = FakeModel(primary_behavior, name="primary")
    fallback = FakeModel(fallback_behavior, name="fb-model")

    monkeypatch.setattr(llm_mod, "build_model", lambda settings: fallback)

    emit = ListEventEmitter()
    result = await run_llm_step(
        {},
        node_id="n",
        system_prompt="s",
        input_keys=[],
        output_model=Out,
        model=primary,
        emit=emit,
        run_id="r",
        call_policy=CallPolicy(
            retry_count=0,
            timeout_seconds=10,
            fallback=ModelSettings(provider="openai", model="gpt-4o"),
        ),
    )
    assert result == {"answer": "fb"}
    logs = [e for e in emit.events if e.event_type == "log" and e.message]
    assert any("fallback" in e.message for e in logs)


async def test_emit_token_usage_populates_usage_sink():
    """If usage_cb.usage_metadata is present, fill prompt/completion/cost into usage_sink."""

    class FakeUsageCallback:
        usage_metadata = {"claude-3": {"input_tokens": 100, "output_tokens": 50}}

    emit = ListEventEmitter()
    usage: dict = {}
    await llm_mod._emit_token_usage(
        FakeUsageCallback(),
        emit=emit,
        run_id="r",
        node_id="n",
        model_name="claude-3",
        usage_sink=usage,
    )
    assert usage["prompt"] == 100
    assert usage["completion"] == 50
    assert usage["cost"] is None  # "claude-3" has no price
    assert any(e.event_type == "log" and e.token_usage for e in emit.events)


async def test_emit_token_usage_without_sink_still_emits_log():
    """Even if usage_sink is None, the existing log event emission is unchanged (regression)."""

    class FakeUsageCallback:
        usage_metadata = {"claude-3": {"input_tokens": 10, "output_tokens": 5}}

    emit = ListEventEmitter()
    await llm_mod._emit_token_usage(
        FakeUsageCallback(), emit=emit, run_id="r", node_id="n", model_name="claude-3"
    )
    assert any(e.event_type == "log" and e.token_usage for e in emit.events)


async def test_fallback_failure_emits_error(monkeypatch):
    """If both primary and fallback fail, error event + re-raise the exception."""
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    def raise_behavior(calls, messages):
        raise RuntimeError("down")

    primary = FakeModel(raise_behavior, name="primary")
    fallback = FakeModel(raise_behavior, name="fb-model")
    monkeypatch.setattr(llm_mod, "build_model", lambda settings: fallback)

    emit = ListEventEmitter()
    with pytest.raises(RuntimeError):
        await run_llm_step(
            {},
            node_id="n",
            system_prompt="s",
            input_keys=[],
            output_model=Out,
            model=primary,
            emit=emit,
            run_id="r",
            call_policy=CallPolicy(
                retry_count=0,
                timeout_seconds=10,
                fallback=ModelSettings(provider="openai", model="gpt-4o"),
            ),
        )
    assert any(e.event_type == "error" for e in emit.events)


def test_cost_for_usage_is_none_without_a_price():
    from models import cost_for_usage

    assert cost_for_usage("no-such-model-xyz", 100, 50) is None
    assert cost_for_usage("claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0


async def test_emit_token_usage_cost_is_none_for_unpriced_model():
    class FakeUsageCallback:
        usage_metadata = {"no-such-model-xyz": {"input_tokens": 10, "output_tokens": 5}}

    emit = ListEventEmitter()
    await llm_mod._emit_token_usage(FakeUsageCallback(), emit=emit, run_id="r", node_id="n")
    assert [e.token_usage["cost"] for e in emit.events] == [None]


async def test_emit_token_usage_prefers_provider_reported_cost():
    class FakeUsageCallback:
        usage_metadata = {"no-such-model-xyz": {"input_tokens": 10, "output_tokens": 5}}
        reported_cost = {"no-such-model-xyz": 0.0123}

    emit = ListEventEmitter()
    await llm_mod._emit_token_usage(FakeUsageCallback(), emit=emit, run_id="r", node_id="n")
    assert [e.token_usage["cost"] for e in emit.events] == [0.0123]


def test_usage_handler_collects_openrouter_reported_cost():
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    msg = AIMessage(
        content="",
        usage_metadata={"input_tokens": 47, "output_tokens": 11, "total_tokens": 58},
        response_metadata={"model_name": "google/gemini-3.1-flash-lite"},
    )
    result = LLMResult(
        generations=[[ChatGeneration(message=msg)]],
        llm_output={"token_usage": {"cost": 2.5e-05}},
    )
    h = llm_mod.UsageCostHandler()
    h.on_llm_end(result)
    h.on_llm_end(result)
    assert h.reported_cost == {"google/gemini-3.1-flash-lite": 5e-05}
    assert h.usage_metadata["google/gemini-3.1-flash-lite"]["input_tokens"] == 94
