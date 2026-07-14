"""run_llm_step 호출 정책 단위 테스트 — retry / timeout / fallback.

가짜 모델로 ainvoke 동작을 제어한다 (AGENTS.md §6). 실제 LLM API 미호출.
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
    """1회 실패 후 재시도에서 성공하면 결과를 반환하고 retry 로그를 남긴다."""
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
    """재시도 전부 소진 후엔 error 이벤트 방출 + 마지막 예외 재발산."""
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
    """ainvoke가 timeout을 초과하면 asyncio.wait_for가 TimeoutError → (retry_count=0) 즉시 실패."""
    # retry_count=0 → backoff sleep 없음. asyncio.sleep은 패치하지 않아 진짜 지연 발생.

    async def behavior(calls, messages):
        await asyncio.sleep(0.3)  # 진짜 지연 — wait_for가 timeout(0.05)에 취소
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
    """주 모델 재시도 소진 후 fallback이 한 번에 성공하면 결과 반환."""
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


async def test_fallback_failure_emits_error(monkeypatch):
    """주+fallback 모두 실패하면 error 이벤트 + 예외 재발산."""
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
