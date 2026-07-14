from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

import config
from logging_config import logger

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


class ClassifyOut(BaseModel):
    """classify 노드 출력 — 매칭된 판단 카드 id 목록."""

    card_ids: list[str] = []
    rationale: str = ""


# ─── Model factory ─────────────────────────────────────────────────────────────


@dataclass
class ModelSettings:
    """컴파일 시점에 확정된 LLM 생성 설정.

    모든 값은 "해당 노드가 명시한 override" 또는 None(=모델 기본값 상속)이다.
    build_model()이 provider별 생성자 인자로 변환한다. camelCase 계약은
    아키텍처 JSON(modelSlots)에만 적용되고, 여기는 내부 Python 필드다.
    """

    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    seed: int | None = None


@dataclass
class CallPolicy:
    """LLM 호출 시점 정책 — build_model이 만든 모델과 별개로, 실제 ainvoke를 감싼다.

    timeout_seconds / retry_count 는 노드 override → 전역 기본값 상속.
    fallback 은 주 모델의 재시도를 전부 소진한 뒤 1회만 시도하는 대체 모델 설정.
    """

    timeout_seconds: float | None = None
    retry_count: int = 0
    fallback: ModelSettings | None = None


def _provider_kwargs(provider: str, s: ModelSettings) -> dict:
    """공통 ModelSettings → provider별 LangChain 생성자 kwargs.

    지원하지 않는 옵션은 경고 로그만 남기고 조용히 누락시킨다 — 저장된 아키텍처가
    다른 provider로 바뀌어도 실행이 불필요하게 깨지지 않게.
    """
    kw: dict = {"model": s.model, "temperature": s.temperature}
    if provider == "anthropic":
        if s.max_tokens is not None:
            kw["max_tokens"] = s.max_tokens
        if s.top_p is not None:
            kw["top_p"] = s.top_p
        if s.stop:
            kw["stop_sequences"] = s.stop
        if s.seed is not None:
            logger.warning("Anthropic은 seed를 지원하지 않음 — 무시 (model=%s)", s.model)
    elif provider == "openai":
        if s.max_tokens is not None:
            kw["max_tokens"] = s.max_tokens
        if s.top_p is not None:
            kw["top_p"] = s.top_p
        if s.stop:
            kw["stop"] = s.stop
        if s.seed is not None:
            kw["seed"] = s.seed
    elif provider == "google":
        if s.max_tokens is not None:
            kw["max_output_tokens"] = s.max_tokens
        if s.top_p is not None:
            kw["top_p"] = s.top_p
        if s.stop:
            kw["stop_sequences"] = s.stop
        if s.seed is not None:
            logger.warning("Google은 seed를 지원하지 않음 — 무시 (model=%s)", s.model)
    elif provider == "local":
        if s.max_tokens is not None:
            kw["max_tokens"] = s.max_tokens
        if s.top_p is not None:
            kw["top_p"] = s.top_p
        if s.stop:
            kw["stop"] = s.stop
        if s.seed is not None:
            kw["seed"] = s.seed
    return kw


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


def build_model(settings: ModelSettings) -> BaseChatModel:
    """ModelSettings → provider별 BaseChatModel.

    공통 설정을 _provider_kwargs가 각 provider의 인자명으로 변환한다.
    API 키 누락은 이 시점(컴파일)에 ValueError로 발생 — run_llm_step이 아니라.
    """
    provider = settings.provider
    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=config.ANTHROPIC_API_KEY, **_provider_kwargs("anthropic", settings)
        )
    elif provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(api_key=config.OPENAI_API_KEY, **_provider_kwargs("openai", settings))
    elif provider == "google":
        if not config.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            google_api_key=config.GOOGLE_API_KEY, **_provider_kwargs("google", settings)
        )
    elif provider == "local":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=config.LOCAL_BASE_URL, api_key="local", **_provider_kwargs("local", settings)
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. Must be 'anthropic', 'openai', 'google', or 'local'."
        )
