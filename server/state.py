from typing import Annotated, TypedDict


class LoopRuntimeState(TypedDict):
    iteration: int
    total_tokens: int
    total_cost_usd: float
    started_at: float
    last_feedback: str | None
    progress_history: list[float]


def empty_loop_runtime() -> LoopRuntimeState:
    return LoopRuntimeState(
        iteration=0,
        total_tokens=0,
        total_cost_usd=0.0,
        started_at=0.0,
        last_feedback=None,
        progress_history=[],
    )


def merge_loop_runtime(
    existing: dict[str, LoopRuntimeState], new: dict[str, LoopRuntimeState]
) -> dict[str, LoopRuntimeState]:
    """LoopPolicy별 loop_runtime 병합 reducer.

    iteration/started_at/last_feedback는 새 값이 있으면 교체한다(단일 writer —
    가드 노드가 iteration/started_at을, review 노드가 last_feedback을 쓴다).
    total_tokens/total_cost_usd/progress_history는 여러 루프 멤버 노드가 각자의
    기여분만 부분 업데이트로 보내므로 누적한다(합산/append).
    """
    merged = dict(existing)
    for policy_id, update in new.items():
        current = merged.get(policy_id, empty_loop_runtime())
        merged[policy_id] = LoopRuntimeState(
            iteration=update.get("iteration", current["iteration"]),
            total_tokens=current["total_tokens"] + update.get("total_tokens", 0),
            total_cost_usd=current["total_cost_usd"] + update.get("total_cost_usd", 0.0),
            started_at=update.get("started_at", current["started_at"]),
            last_feedback=update.get("last_feedback", current["last_feedback"]),
            progress_history=current["progress_history"] + update.get("progress_history", []),
        )
    return merged


class AgentState(TypedDict):
    task: str
    task_tags: list[str]
    intent: str | None  # 원본 의도 — 없으면 review가 task 자체를 의도로 간주
    plan: list[str] | None
    answer: str | None
    confidence: float | None  # ReasonOut 참고 지표 (라우팅 미사용)
    criteria: list[dict]  # Criterion.model_dump() 목록
    review_delta: dict | None  # ReviewDelta.model_dump()
    review_branch: str | None  # review 노드가 확정한 accept/refine/clarify (라우터가 읽음)
    retries: int
    feedback: str | None  # 직전 리뷰의 unmet delta → 재작업 입력
    batch_mode: bool  # True면 clarify → accept 강등 (interrupt 불가 환경)
    matched_cards: list[str]  # classify가 매칭한 판단 카드 id 목록
    loop_runtime: Annotated[dict[str, LoopRuntimeState], merge_loop_runtime]


def initial_state(
    task: str,
    task_tags: list[str] | None = None,
    batch_mode: bool = False,
    intent: str | None = None,
    criteria: list[dict] | None = None,
) -> AgentState:
    return AgentState(
        task=task,
        task_tags=task_tags or [],
        intent=intent,
        plan=None,
        answer=None,
        confidence=None,
        criteria=criteria or [],
        review_delta=None,
        review_branch=None,
        retries=0,
        feedback=None,
        batch_mode=batch_mode,
        matched_cards=[],
        loop_runtime={},
    )
