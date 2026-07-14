from typing import TypedDict


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
    )
