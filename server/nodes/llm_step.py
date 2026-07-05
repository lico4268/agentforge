import json
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from events import EventEmitter, make_error_event, make_event
from logging_config import logger
from models import cost_for_usage
from state import AgentState


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(i, str) for i in value):
        return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(value))
    return json.dumps(value, ensure_ascii=False, indent=2)


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
) -> dict:
    blocks = []
    for state_key, label in input_keys:
        value = state.get(state_key)
        if value is None:
            continue
        rendered = _render(value)
        blocks.append(f"## {label}\n{rendered}")

    human_content = "\n\n".join(blocks)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]

    structured = model.with_structured_output(output_model)
    # 구조화 출력은 usage metadata를 감추므로 콜백으로 토큰 사용량을 수집한다.
    usage_cb = UsageMetadataCallbackHandler()
    invoke_config = {"callbacks": [usage_cb]}
    try:
        result = await structured.ainvoke(messages, config=invoke_config)
    except Exception as first_err:
        # 1회 복구 재시도
        recovery_messages = messages + [
            HumanMessage(content=f"Output validation error: {first_err}\nPlease fix and retry.")
        ]
        try:
            result = await structured.ainvoke(recovery_messages, config=invoke_config)
        except Exception as second_err:
            logger.error("node %r failed: %s", node_id, second_err)
            await emit(make_error_event(run_id, node_id, second_err))
            raise

    await _emit_token_usage(usage_cb, emit=emit, run_id=run_id, node_id=node_id)
    return result.model_dump()


async def _emit_token_usage(
    usage_cb: UsageMetadataCallbackHandler,
    *,
    emit: EventEmitter,
    run_id: str,
    node_id: str,
) -> None:
    """수집된 usage를 'log' 이벤트의 token_usage로 방출.

    프론트 계약(prompt/completion — 어느 이벤트든 tokenUsage가 있으면 노드에 합산)과
    하니스 계약(total_tokens/cost 집계)을 한 dict에 함께 담는다. 비었으면 방출 생략.
    """
    prompt = completion = 0
    cost = 0.0
    for model_name, usage in (usage_cb.usage_metadata or {}).items():
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        prompt += in_tok
        completion += out_tok
        cost += cost_for_usage(model_name, in_tok, out_tok)
    if prompt == 0 and completion == 0:
        return
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
            },
        )
    )
