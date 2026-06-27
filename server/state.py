from typing import TypedDict


class AgentState(TypedDict):
    task: str
    task_tags: list[str]
    plan: list[str] | None
    answer: str | None
    confidence: float | None
    verdict: dict | None          # {"passed": bool, "feedback": str}
    retries: int
    feedback: str | None          # 직전 검증 피드백 → 재시도 입력
    batch_mode: bool              # True면 Human Checkpoint 우회


def initial_state(task: str, task_tags: list[str] | None = None, batch_mode: bool = False) -> AgentState:
    return AgentState(
        task=task,
        task_tags=task_tags or [],
        plan=None,
        answer=None,
        confidence=None,
        verdict=None,
        retries=0,
        feedback=None,
        batch_mode=batch_mode,
    )
