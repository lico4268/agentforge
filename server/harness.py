"""
v0.1 벤치마크 하니스: run_dataset + GSM8K grader + Report
"""
import re
import uuid
from typing import Callable
from pydantic import BaseModel

from state import AgentState, initial_state
from events import ListEventEmitter


class Item(BaseModel):
    question: str
    gold: str
    tags: list[str] = []


class Report(BaseModel):
    pass_at_1: float
    avg_tokens: float
    avg_cost: float
    verify_rate_easy: float    # 쉬운 문항(confidence≥0.85) 중 검증 발동 비율
    verify_rate_hard: float
    escalation_rate: float     # batch에서 human→auto 강등 비율


def gsm8k_grader(answer: str | None, gold: str) -> bool:
    if not answer:
        return False
    nums_answer = re.findall(r"-?\d+(?:\.\d+)?", answer)
    nums_gold = re.findall(r"-?\d+(?:\.\d+)?", gold)
    if not nums_answer or not nums_gold:
        return False
    return nums_answer[-1] == nums_gold[-1]


async def run_dataset(
    build_graph: Callable,
    items: list[Item],
    grader: Callable[[str | None, str], bool] = gsm8k_grader,
) -> Report:
    results = []
    total_tokens = 0
    total_cost = 0.0
    verify_fired_easy = 0
    verify_fired_hard = 0
    easy_count = 0
    hard_count = 0
    escalation_count = 0

    for item in items:
        emitter = ListEventEmitter()
        run_id = str(uuid.uuid4())
        graph = build_graph(emitter=emitter, run_id=run_id)

        state0 = initial_state(
            task=item.question,
            task_tags=item.tags,
            batch_mode=True,
        )
        config = {"configurable": {"thread_id": run_id}}

        try:
            final: AgentState = await graph.ainvoke(state0, config=config)
        except Exception:
            final = state0  # type: ignore

        ok = grader(final.get("answer"), item.gold)
        results.append(ok)

        # 이벤트에서 지표 집계
        for ev in emitter.events:
            if ev.event_type == "token_usage":
                total_tokens += ev.payload.get("total_tokens", 0)
                total_cost += ev.payload.get("cost", 0.0)
            if ev.event_type == "policy_decision":
                branch = ev.payload.get("branch", "")
                conf = final.get("confidence") or 0.0
                if conf >= 0.85:
                    easy_count += 1
                    if branch in ("auto", "human"):
                        verify_fired_easy += 1
                else:
                    hard_count += 1
                    if branch in ("auto", "human"):
                        verify_fired_hard += 1
                if branch == "auto" and "human" in str(ev.payload.get("reason", "")):
                    escalation_count += 1

    n = len(results)
    return Report(
        pass_at_1=sum(results) / n if n else 0.0,
        avg_tokens=total_tokens / n if n else 0.0,
        avg_cost=total_cost / n if n else 0.0,
        verify_rate_easy=verify_fired_easy / easy_count if easy_count else 0.0,
        verify_rate_hard=verify_fired_hard / hard_count if hard_count else 0.0,
        escalation_rate=escalation_count / n if n else 0.0,
    )
