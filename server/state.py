from typing import Annotated, Any, TypedDict


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


def merge_vars(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """사용자 정의 role 값 버킷(vars)의 병합 reducer — 얕은 병합, 키가 겹치면 새
    값이 이긴다. 여러 노드가 같은 수퍼스텝에 서로 다른 키를 써도 충돌 없다."""
    return {**existing, **new}


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
    # 사용자 정의 노드 타입(Phase B)의 role 값 — 여기 없는 키는 LangGraph 채널이
    # 없어 조용히 버려지므로, 위에 없는 role은 전부 이 버킷에 산다.
    vars: Annotated[dict[str, Any], merge_vars]


# AgentState에 실제 채널이 있는 키 집합 — read_state_value/write_state_value가
# "알려진 최상위 키 vs vars에 담을 사용자 정의 키"를 가르는 기준.
KNOWN_STATE_KEYS = frozenset(AgentState.__annotations__.keys())


def read_state_value(state: AgentState, key: str) -> Any:
    """알려진 키는 최상위에서, 아니면 vars에서 읽는다."""
    if key in KNOWN_STATE_KEYS:
        return state.get(key)
    return (state.get("vars") or {}).get(key)


def write_state_value(updates: dict[str, Any], key: str, value: Any) -> None:
    """read_state_value의 반대 — 알려진 키는 updates 최상위에, 아니면
    updates['vars']에 쓴다(같은 updates dict에 여러 번 불러도 누적됨)."""
    if key in KNOWN_STATE_KEYS:
        updates[key] = value
    else:
        updates.setdefault("vars", {})[key] = value


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
        vars={},
    )
