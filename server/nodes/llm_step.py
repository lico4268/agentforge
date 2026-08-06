import asyncio
import json
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

import config
from events import EventEmitter, make_error_event, make_event
from logging_config import logger
from models import CallPolicy, build_model, cost_for_usage
from state import AgentState


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(i, str) for i in value):
        return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(value))
    return json.dumps(value, ensure_ascii=False, indent=2)


def _model_name(model: BaseChatModel) -> str:
    return getattr(model, "model", None) or getattr(model, "model_name", None) or ""


def _default_policy() -> CallPolicy:
    return CallPolicy(timeout_seconds=config.NODE_TIMEOUT, retry_count=config.LLM_RETRY_COUNT)


async def run_llm_step(
    state: AgentState,
    *,
    node_id: str,
    system_prompt: str,
    input_keys: list[tuple[str, str]],  # [(state_key, label), ...]
    output_model: type[BaseModel],
    model: BaseChatModel,
    emit: EventEmitter,
    run_id: str,
    call_policy: CallPolicy | None = None,
    usage_sink: dict | None = None,
) -> dict:
    policy = call_policy or _default_policy()
    timeout = float(policy.timeout_seconds or config.NODE_TIMEOUT)
    retry_count = max(0, int(policy.retry_count))

    blocks = []
    for state_key, label in input_keys:
        value = state.get(state_key)
        if value is None:
            continue
        rendered = _render(value)
        blocks.append(f"## {label}\n{rendered}")

    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="\n\n".join(blocks)),
    ]
    structured = model.with_structured_output(output_model)
    # 구조화 출력은 usage metadata를 감추므로 콜백으로 토큰 사용량을 수집한다.
    # primary 재시도 + fallback 모두 같은 핸들러에 누적 → 비용/토큰 합산이 정확하다.
    usage_cb = UsageMetadataCallbackHandler()
    invoke_config = {"callbacks": [usage_cb]}

    last_err: BaseException | None = None
    used_model_name = _model_name(model)

    async def _attempt(m, cfg) -> BaseModel:
        return await asyncio.wait_for(m.ainvoke(messages, config=cfg), timeout=timeout)

    # ── primary: 최대 (retry_count + 1)회 시도 ──────────────────────────────────
    for attempt in range(retry_count + 1):
        try:
            result = await _attempt(structured, invoke_config)
            await _emit_token_usage(
                usage_cb,
                emit=emit,
                run_id=run_id,
                node_id=node_id,
                model_name=used_model_name,
                attempt=attempt,
                fallback_used=False,
                usage_sink=usage_sink,
            )
            return result.model_dump()
        except Exception as err:  # noqa: BLE001 — 광범위 재시도 대상
            last_err = err
            if attempt < retry_count:
                logger.warning(
                    "node %r attempt %d failed: %s — retrying", node_id, attempt + 1, err
                )
                await emit(
                    make_event(
                        run_id,
                        node_id,
                        "log",
                        message=f"retry {attempt + 1}/{retry_count}: {type(err).__name__}: {err}",
                    )
                )
                # 출력 검증 실패에 대비해 교정 힌트를 붙여 재시도 (기존 1회 복구 정책의 일반화)
                messages = messages + [
                    HumanMessage(content=f"Previous attempt failed: {err}\nPlease fix and retry.")
                ]
                await asyncio.sleep(min(2**attempt, 8))
            else:
                logger.error("node %r failed after %d attempts: %s", node_id, attempt + 1, err)

    # ── fallback: 재시도 소진 후 1회만 (재시도 없음) ────────────────────────────
    if policy.fallback is not None:
        try:
            fallback_model = build_model(policy.fallback)
            used_model_name = _model_name(fallback_model)
            await emit(
                make_event(
                    run_id,
                    node_id,
                    "log",
                    message=f"fallback → {policy.fallback.provider}/{policy.fallback.model}",
                )
            )
            fallback_structured = fallback_model.with_structured_output(output_model)
            result = await _attempt(fallback_structured, invoke_config)
            await _emit_token_usage(
                usage_cb,
                emit=emit,
                run_id=run_id,
                node_id=node_id,
                model_name=used_model_name,
                attempt=0,
                fallback_used=True,
                usage_sink=usage_sink,
            )
            return result.model_dump()
        except Exception as err:  # noqa: BLE001
            last_err = err
            logger.error("node %r fallback failed: %s", node_id, err)

    # 전부 실패 — 표준 error 이벤트 방출 후 재발산
    if last_err is not None:
        await emit(make_error_event(run_id, node_id, last_err))
        raise last_err
    # 도달 불가 — 안전망
    raise RuntimeError(f"node {node_id!r} produced no result")


async def _emit_token_usage(
    usage_cb: UsageMetadataCallbackHandler,
    *,
    emit: EventEmitter,
    run_id: str,
    node_id: str,
    model_name: str = "",
    attempt: int = 0,
    fallback_used: bool = False,
    usage_sink: dict | None = None,
) -> None:
    """수집된 usage를 'log' 이벤트의 token_usage로 방출.

    프론트 계약(prompt/completion)과 하니스 계약(total_tokens/cost)을 한 dict에 담는다.
    관측 메타(model/attempt/fallbackUsed)도 함께 — 프론트 Metrics에 표시.
    비었으면 방출 생략.
    """
    prompt = completion = 0
    cost = 0.0
    for name, usage in (usage_cb.usage_metadata or {}).items():
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        prompt += in_tok
        completion += out_tok
        cost += cost_for_usage(name, in_tok, out_tok)
    if prompt == 0 and completion == 0:
        return
    if usage_sink is not None:
        usage_sink["prompt"] = prompt
        usage_sink["completion"] = completion
        usage_sink["cost"] = cost
    await emit(
        make_event(
            run_id,
            node_id,
            "log",
            token_usage={
                "prompt": prompt,
                "completion": completion,
                "total_tokens": prompt + completion,
                "cost": cost,
                "model": model_name,
                "attempt": attempt,
                "fallbackUsed": fallback_used,
            },
        )
    )
