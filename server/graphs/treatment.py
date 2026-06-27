"""
gsm8k-treatment: Input → Planning → Reasoning → Review Policy
  ├ pass  → Output
  ├ auto  → Auto-Verify → pass → Output / fail → Reasoning (retry)
  └ human → Human Checkpoint → approve/revise/reject
"""
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import AgentState
from events import EventEmitter, make_event
from models import PlanOut, ReasonOut, VerdictOut
from nodes.llm_step import run_llm_step
from nodes.policy import compute_branch, make_route_review, make_route_verify
from nodes.checkpoint import make_human_checkpoint
from config import MAX_RETRIES

PLANNING_SYSTEM_PROMPT = """\
You are a planning assistant. Decompose the given task into an ordered list of steps.
Return the steps as a JSON array of strings."""

REASONING_SYSTEM_PROMPT = """\
You are a math reasoning assistant. Solve the given task step by step following the plan.
If there is previous feedback, use it to improve your answer.
Return your final answer and a confidence score between 0 and 1."""

VERIFY_SYSTEM_PROMPT = """\
You are a strict math answer verifier. Check whether the given answer is correct for the task.
Return whether it passed and detailed feedback."""


def build_treatment(model: BaseChatModel, emit: EventEmitter, run_id: str):
    route_review = make_route_review()
    route_verify = make_route_verify()
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
        await emit(make_event(run_id, "reasoning", "node_end",
                              output={"answer": result["answer"], "confidence": result["confidence"]}))
        return {"answer": result["answer"], "confidence": result["confidence"]}

    async def review_policy(state: AgentState) -> dict:
        await emit(make_event(run_id, "review_policy", "node_start"))
        # 여기서 emit (async 가능). sync 라우터는 같은 로직만 순수하게 반복.
        branch = compute_branch(state)
        c = state.get("confidence") or 0.0
        await emit(make_event(
            run_id, "review_policy", "node_end",
            policy_decision={
                "activated": branch != "pass",
                "reason": f"conf {c:.2f} → {branch}",
            },
        ))
        return {}

    async def auto_verify(state: AgentState) -> dict:
        await emit(make_event(run_id, "auto_verify", "node_start"))
        result = await run_llm_step(
            state,
            node_id="auto_verify",
            system_prompt=VERIFY_SYSTEM_PROMPT,
            input_keys=[("task", "Task"), ("answer", "Answer")],
            output_model=VerdictOut,
            model=model,
            emit=emit,
            run_id=run_id,
        )
        await emit(make_event(run_id, "auto_verify", "node_end",
                              output={"passed": result["passed"], "feedback": result["feedback"]}))
        verdict = {"passed": result["passed"], "feedback": result["feedback"]}
        return {
            "verdict": verdict,
            "feedback": result["feedback"],
            "retries": state.get("retries", 0) + 1,
        }

    async def output_node(state: AgentState) -> dict:
        await emit(make_event(run_id, "output", "node_end",
                              output={"answer": state.get("answer"), "verdict": state.get("verdict")}))
        return {}

    graph = StateGraph(AgentState)
    graph.add_node("planning", planning)
    graph.add_node("reasoning", reasoning)
    graph.add_node("review_policy", review_policy)
    graph.add_node("auto_verify", auto_verify)
    graph.add_node("human_checkpoint", human_checkpoint)
    graph.add_node("output", output_node)

    graph.set_entry_point("planning")
    graph.add_edge("planning", "reasoning")
    graph.add_edge("reasoning", "review_policy")

    graph.add_conditional_edges(
        "review_policy",
        route_review,
        {"pass": "output", "auto": "auto_verify", "human": "human_checkpoint"},
    )

    graph.add_conditional_edges(
        "auto_verify",
        route_verify,
        {"output": "output", "retry": "reasoning"},
    )

    graph.add_edge("output", END)

    checkpointer = MemorySaver()
    return graph.compile(
        checkpointer=checkpointer,
        recursion_limit=MAX_RETRIES * 10 + 20,
    )
