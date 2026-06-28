from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

import config

# ─── Output schemas ────────────────────────────────────────────────────────────

class PlanOut(BaseModel):
    steps: list[str]


class ReasonOut(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


class VerdictOut(BaseModel):
    passed: bool
    feedback: str


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
