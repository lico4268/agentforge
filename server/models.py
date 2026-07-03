from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

import config

# ─── Output schemas ────────────────────────────────────────────────────────────


class PlanOut(BaseModel):
    steps: list[str]


class ReasonOut(BaseModel):
    answer: str
    # 참고 지표로만 잔존 — 라우팅에는 사용하지 않는다 (POLICY_REDESIGN.md §1)
    confidence: float = Field(ge=0.0, le=1.0)


# ─── Review schemas (POLICY_REDESIGN.md §4) ────────────────────────────────────


class Criterion(BaseModel):
    id: str
    text: str  # 이진 판정 가능한 한 문장
    severity: Literal["must_pass", "should_pass"] = "must_pass"
    impl: Literal["llm", "code", "reminder"] = "llm"  # Phase 1은 llm만 실행
    code: str | None = None
    source: Literal["agent", "human"] = "human"
    status: Literal["proposed", "confirmed"] = "confirmed"
    examples: list[str] = []
    note: str = ""


class CriterionVerdict(BaseModel):
    id: str  # 대상 Criterion.id
    verdict: Literal["met", "unmet", "unsure"]
    evidence: str  # 결과물에서 인용한 근거 1개


class ReviewDelta(BaseModel):
    """리뷰 출력 = diff. score 필드 없음 — confidence 재림 방지."""

    per_criterion: list[CriterionVerdict] = []
    misalignments: list[str] = []
    elicit_questions: list[str] = []
    proposed_criteria: list[str] = []
    reroute_hint: str = ""


# ─── Model factory ─────────────────────────────────────────────────────────────


def build_model(
    provider: str,
    model: str,
    temperature: float = 0.0,
) -> BaseChatModel:
    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=config.ANTHROPIC_API_KEY,
        )
    elif provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=config.OPENAI_API_KEY,
        )
    elif provider == "google":
        if not config.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=config.GOOGLE_API_KEY,
        )
    elif provider == "local":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=config.LOCAL_BASE_URL,
            api_key="local",
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. Must be 'anthropic', 'openai', 'google', or 'local'."
        )
