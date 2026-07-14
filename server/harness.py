"""
v0.1 벤치마크 하니스: run_dataset + GSM8K grader + Report
"""

import re
import uuid
from collections.abc import Callable

from pydantic import BaseModel

from events import ListEventEmitter
from logging_config import logger
from state import AgentState, initial_state


class Item(BaseModel):
    question: str
    gold: str
    tags: list[str] = []


class Report(BaseModel):
    pass_at_1: float
    avg_tokens: float
    avg_cost: float
    refine_rate: float  # 리뷰 판정 중 refine(재작업) 비율
    clarify_rate: float  # 리뷰 판정 중 clarify(인간 개입) 비율 — batch 강등 포함
    demotion_rate: float  # batch에서 clarify → accept 강등 비율 (문항당)
    error_rate: float  # 문항 실행 중 예외 발생 비율
    card_match_rate: float  # 매칭 카드 ≥1개인 문항 비율


def gsm8k_grader(answer: str | None, gold: str) -> bool:
    if not answer:
        return False
    # 천단위 콤마 제거 후 숫자 추출 — 마지막 숫자를 수치로 비교 ("72.0" == "72")
    nums_answer = re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))
    nums_gold = re.findall(r"-?\d+(?:\.\d+)?", gold.replace(",", ""))
    if not nums_answer or not nums_gold:
        return False
    try:
        return float(nums_answer[-1]) == float(nums_gold[-1])
    except (TypeError, ValueError):
        return False


async def run_dataset(
    build_graph: Callable,
    items: list[Item],
    grader: Callable[[str | None, str], bool] = gsm8k_grader,
) -> Report:
    results: list[bool] = []
    total_tokens = 0
    total_cost = 0.0
    decision_count = 0
    refine_count = 0
    clarify_count = 0
    demotion_count = 0
    error_count = 0
    card_match_count = 0
    consecutive = 0  # 연속 예외 카운터 — 성공 문항이 나오면 리셋
    abort_threshold = 5

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
        except Exception as exc:
            logger.error("benchmark item failed: %s | question=%.80s", exc, item.question)
            error_count += 1
            consecutive += 1
            results.append(False)
            if consecutive >= abort_threshold:
                raise RuntimeError(
                    f"aborting: {consecutive} consecutive item failures"
                    " — check API key/model config"
                ) from exc
            continue

        # 예외 없이 완료한 문항이면 연속 실패 카운터 리셋
        consecutive = 0

        if final.get("matched_cards"):
            card_match_count += 1

        ok = grader(final.get("answer"), item.gold)
        results.append(ok)

        # 이벤트에서 지표 집계 — 리뷰 판정은 node_end 이벤트의 policy_decision 필드로 나온다
        for ev in emitter.events:
            if ev.token_usage:
                total_tokens += ev.token_usage.get("total_tokens", 0)
                total_cost += ev.token_usage.get("cost", 0.0)
            decision = ev.policy_decision
            if decision:
                decision_count += 1
                branch = decision.get("branch", "")
                if branch == "refine":
                    refine_count += 1
                if branch == "clarify" or decision.get("demoted"):
                    clarify_count += 1
                if decision.get("demoted"):
                    demotion_count += 1

    n = len(results)
    return Report(
        pass_at_1=sum(results) / n if n else 0.0,
        avg_tokens=total_tokens / n if n else 0.0,
        avg_cost=total_cost / n if n else 0.0,
        refine_rate=refine_count / decision_count if decision_count else 0.0,
        clarify_rate=clarify_count / decision_count if decision_count else 0.0,
        demotion_rate=demotion_count / n if n else 0.0,
        error_rate=error_count / n if n else 0.0,
        card_match_rate=card_match_count / n if n else 0.0,
    )
