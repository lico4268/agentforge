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


def cost_for_usage(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """config.yaml models.pricing 기준 USD 비용. 단가 미등록 모델은 0.0.

    provider가 붙이는 접두어("models/gemini-...")와 config id가 어긋날 수 있어
    정확 일치 → 부분 일치 순으로 조회한다.
    """
    pricing = config.PRICING.get(model_name)
    if pricing is None:
        for key, value in config.PRICING.items():
            if key in model_name or model_name in key:
                pricing = value
                break
    if not pricing:
        return 0.0
    return (
        input_tokens * float(pricing.get("input", 0)) / 1_000_000
        + output_tokens * float(pricing.get("output", 0)) / 1_000_000
    )


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
