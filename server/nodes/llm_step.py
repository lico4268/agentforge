import json
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from events import EventEmitter, make_event
from state import AgentState


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(i, str) for i in value):
        return "\n".join(f"{i+1}. {s}" for i, s in enumerate(value))
    return json.dumps(value, ensure_ascii=False, indent=2)


async def run_llm_step(
    state: AgentState,
    *,
    node_id: str,
    system_prompt: str,
    input_keys: list[tuple[str, str]],   # [(state_key, label), ...]
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
    try:
        result = await structured.ainvoke(messages)
    except Exception as first_err:
        # 1회 복구 재시도
        recovery_messages = messages + [HumanMessage(content=f"Output validation error: {first_err}\nPlease fix and retry.")]
        try:
            result = await structured.ainvoke(recovery_messages)
        except Exception as second_err:
            await emit(make_event(run_id, node_id, "error", message=str(second_err)))
            raise

    return result.model_dump()
