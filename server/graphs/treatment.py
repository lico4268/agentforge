"""
gsm8k-treatment: Input → Classify (판단 카드 매칭) → Planning → Reasoning
  → Review (intent×criteria diff)
  ├ accept  → Output
  ├ refine  → Reasoning (unmet delta만 피드백으로 재작업)
  └ clarify → Human Checkpoint → approve/revise/reject
"""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from events import EventEmitter, make_event
from models import PlanOut, ReasonOut
from nodes.checkpoint import make_human_checkpoint
from nodes.classify import make_classify
from nodes.llm_step import run_llm_step
from nodes.policy import make_route_review
from nodes.review import make_review
from state import AgentState

PLANNING_SYSTEM_PROMPT = """\
You are a planning assistant. Decompose the given task into an ordered list of steps.
Return the steps as a JSON array of strings."""

REASONING_SYSTEM_PROMPT = """\
You are a math reasoning assistant. Solve the given task step by step following the plan.
If there is previous feedback, use it to improve your answer.
Return your final answer and a confidence score between 0 and 1."""


def build_treatment(model: BaseChatModel, emit: EventEmitter, run_id: str):
    classify = make_classify(model=model, emit=emit, run_id=run_id)
    review = make_review(model=model, emit=emit, run_id=run_id)
    route_review = make_route_review()
    human_checkpoint = make_human_checkpoint(emit, run_id)

    async def planning(state: AgentState) -> dict:
        await emit(make_event(run_id, "planning", "node_start"))
        result = await run_llm_step(
            state,
            node_id="planning",
            system_prompt=PLANNING_SYSTEM_PROMPT,
            input_keys=[("task", "Task")],
            output_model=PlanOut,
            model=model,
            emit=emit,
            run_id=run_id,
        )
        await emit(make_event(run_id, "planning", "node_end", output={"plan": result["steps"]}))
        return {"plan": result["steps"]}

    async def reasoning(state: AgentState) -> dict:
        await emit(make_event(run_id, "reasoning", "node_start"))
        result = await run_llm_step(
            state,
            node_id="reasoning",
            system_prompt=REASONING_SYSTEM_PROMPT,
            input_keys=[("task", "Task"), ("plan", "Plan"), ("feedback", "Previous Feedback")],
            output_model=ReasonOut,
            model=model,
            emit=emit,
            run_id=run_id,
        )
        await emit(
            make_event(
                run_id,
                "reasoning",
                "node_end",
                output={"answer": result["answer"], "confidence": result["confidence"]},
            )
        )
        return {"answer": result["answer"], "confidence": result["confidence"]}

    async def output_node(state: AgentState) -> dict:
        await emit(
            make_event(
                run_id,
                "output",
                "node_end",
                output={"answer": state.get("answer"), "review": state.get("review_delta")},
            )
        )
        return {}

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("planning", planning)
    graph.add_node("reasoning", reasoning)
    graph.add_node("review", review)
    graph.add_node("human_checkpoint", human_checkpoint)
    graph.add_node("output", output_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "planning")
    graph.add_edge("planning", "reasoning")
    graph.add_edge("reasoning", "review")

    graph.add_conditional_edges(
        "review",
        route_review,
        {"accept": "output", "refine": "reasoning", "clarify": "human_checkpoint"},
    )

    graph.add_edge("output", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
