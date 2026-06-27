"""
gsm8k-baseline: Input → Reasoning → Output
검증 구조 없이 단순 추론만 하는 베이스라인.
"""
from functools import partial
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import AgentState
from events import EventEmitter, make_event
from models import ReasonOut
from nodes.llm_step import run_llm_step

REASONING_SYSTEM_PROMPT = """\
You are a math reasoning assistant. Solve the given task step by step.
Return your final answer and a confidence score between 0 and 1."""


def build_baseline(model: BaseChatModel, emit: EventEmitter, run_id: str):
    async def reasoning(state: AgentState) -> dict:
        await emit(make_event(run_id, "reasoning", "node_start"))
        result = await run_llm_step(
            state,
            node_id="reasoning",
            system_prompt=REASONING_SYSTEM_PROMPT,
            input_keys=[("task", "Task"), ("feedback", "Previous Feedback")],
            output_model=ReasonOut,
            model=model,
            emit=emit,
            run_id=run_id,
        )
        await emit(make_event(run_id, "reasoning", "node_end", **result))
        return {"answer": result["answer"], "confidence": result["confidence"]}

    async def output_node(state: AgentState) -> dict:
        await emit(make_event(run_id, "output", "node_end",
                              answer=state.get("answer"),
                              verdict=state.get("verdict")))
        return {}

    graph = StateGraph(AgentState)
    graph.add_node("reasoning", reasoning)
    graph.add_node("output", output_node)

    graph.set_entry_point("reasoning")
    graph.add_edge("reasoning", "output")
    graph.add_edge("output", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
