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
    # Kept only as a reference metric — not used for routing (POLICY_REDESIGN.md §1)
    confidence: float = Field(ge=0.0, le=1.0)


# ─── Review schemas (POLICY_REDESIGN.md §4) ────────────────────────────────────


class Criterion(BaseModel):
    id: str
    text: str  # one sentence that can be judged as binary
    severity: Literal["must_pass", "should_pass"] = "must_pass"
    impl: Literal["llm", "code", "reminder"] = "llm"  # Phase 1 executes llm only
    code: str | None = None
    source: Literal["agent", "human"] = "human"
    status: Literal["proposed", "confirmed"] = "confirmed"
    examples: list[str] = []
    note: str = ""


class CriterionVerdict(BaseModel):
    id: str  # target Criterion.id
    verdict: Literal["met", "unmet", "unsure"]
    evidence: str  # one piece of evidence quoted from the result


class ReviewDelta(BaseModel):
    """Review output = diff. No score field — prevents confidence from coming back."""

    per_criterion: list[CriterionVerdict] = []
    misalignments: list[str] = []
    elicit_questions: list[str] = []
    proposed_criteria: list[str] = []
    reroute_hint: str = ""


class ClassifyOut(BaseModel):
    """classify node output — list of matched judgment card ids."""

    card_ids: list[str] = []
    rationale: str = ""


# ─── Model factory ─────────────────────────────────────────────────────────────


@dataclass
class ModelSettings:
    """LLM generation settings fixed at compile time.

    Every value is either "an override the node specified" or None (= inherit the model default).
    build_model() converts these to provider-specific constructor args. The camelCase contract
    applies only to the architecture JSON (modelSlots); these are internal Python fields.
    """

    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    seed: int | None = None
    # OpenRouter only — takes the provider reasoning parameter normalized to "low"/"medium"/"high".
    reasoning_effort: Literal["low", "medium", "high"] | None = None


@dataclass
class CallPolicy:
    """LLM call-time policy — separate from the model build_model creates, wraps the actual ainvoke.

    timeout_seconds / retry_count: node override → inherit global default.
    fallback is the replacement model config tried once after the primary's retries are exhausted.
    """

    timeout_seconds: float | None = None
    retry_count: int = 0
    fallback: ModelSettings | None = None


def _provider_kwargs(provider: str, s: ModelSettings) -> dict:
    """Common ModelSettings → provider-specific LangChain constructor kwargs.

    Unsupported options are dropped quietly with only a warning log — so a saved architecture
    doesn't break needlessly when switched to a different provider.
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
            logger.warning("Anthropic does not support seed — ignoring (model=%s)", s.model)
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
            logger.warning("Google does not support seed — ignoring (model=%s)", s.model)
    elif provider in ("local", "openrouter"):
        if s.max_tokens is not None:
            kw["max_tokens"] = s.max_tokens
        if s.top_p is not None:
            kw["top_p"] = s.top_p
        if s.stop:
            kw["stop"] = s.stop
        if s.seed is not None:
            kw["seed"] = s.seed
        if provider == "openrouter" and s.reasoning_effort is not None:
            kw["extra_body"] = {"reasoning": {"effort": s.reasoning_effort}}
    return kw


def cost_for_usage(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost based on config.yaml models.pricing. None for models with no registered price —
    a wrong $0 is worse than an unknown.

    The prefix a provider adds ("models/gemini-...") may differ from the config id, so
    lookup is exact match first, then partial match.
    """
    pricing = config.PRICING.get(model_name)
    if pricing is None:
        for key, value in config.PRICING.items():
            if key in model_name or model_name in key:
                pricing = value
                break
    if not pricing:
        return None
    return (
        input_tokens * float(pricing.get("input", 0)) / 1_000_000
        + output_tokens * float(pricing.get("output", 0)) / 1_000_000
    )


def build_model(settings: ModelSettings) -> BaseChatModel:
    """ModelSettings → provider-specific BaseChatModel.

    _provider_kwargs converts the common settings to each provider's argument names.
    A missing API key raises ValueError at this point (compile time) — not in run_llm_step.
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
    elif provider == "openrouter":
        if not config.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            **_provider_kwargs("openrouter", settings),
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. Must be 'anthropic', 'openai', 'google', 'local', "
            "or 'openrouter'."
        )
