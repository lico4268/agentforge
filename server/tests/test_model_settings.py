"""모델 설정 해석 단위 테스트.

override 우선순위(노드 slot → config.yaml 모델 기본값 → 전역)와
provider별 인자 매핑(_provider_kwargs)을 검증한다. LLM은 호출하지 않는다 (AGENTS.md §6).
"""

import config
import graphs.compile as compile_mod
import models
from models import CallPolicy, ModelSettings


def test_config_model_defaults():
    md = config.model_defaults("gemini-3.1-flash-lite")
    assert md["temperature"] == 0.0
    assert md["max_tokens"] == 4096
    assert config.model_defaults("no-such-model") == {}


def test_provider_kwargs_anthropic():
    s = ModelSettings(
        "anthropic", "claude", temperature=0.5, max_tokens=1000, top_p=0.9, stop=["END"], seed=7
    )
    kw = models._provider_kwargs("anthropic", s)
    assert kw["max_tokens"] == 1000
    assert kw["top_p"] == 0.9
    assert kw["stop_sequences"] == ["END"]
    assert "seed" not in kw  # anthropic 미지원 — 무시


def test_provider_kwargs_google():
    s = ModelSettings("google", "gemini", temperature=0.5, max_tokens=512, top_p=0.9, stop=["x"])
    kw = models._provider_kwargs("google", s)
    assert kw["max_output_tokens"] == 512
    assert kw["stop_sequences"] == ["x"]
    assert "max_tokens" not in kw


def test_provider_kwargs_openai_seed_and_stop():
    s = ModelSettings("openai", "gpt", temperature=0.5, seed=42, stop=["END"])
    kw = models._provider_kwargs("openai", s)
    assert kw["seed"] == 42
    assert kw["stop"] == ["END"]


def test_provider_kwargs_skips_none():
    s = ModelSettings("anthropic", "claude", temperature=0.5)
    kw = models._provider_kwargs("anthropic", s)
    assert kw == {"model": "claude", "temperature": 0.5}


def test_resolve_slot_overrides_model_defaults():
    slot = {
        "provider": "google",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.2,
        "maxTokens": 800,
        "topP": 0.95,
        "stopSequences": ["END", ""],
        "seed": 3,
        "timeoutSeconds": 30,
        "retryCount": 2,
        "fallback": {"provider": "openai", "model": "gpt-4o"},
    }
    settings, policy = compile_mod._settings_from_slot(slot)
    assert settings.max_tokens == 800  # override가 모델 기본값(4096) 이김
    assert settings.top_p == 0.95
    assert settings.stop == ["END"]  # 빈 문자열 제거
    assert settings.seed == 3
    assert settings.temperature == 0.2
    assert policy.timeout_seconds == 30
    assert policy.retry_count == 2
    assert policy.fallback is not None
    assert policy.fallback.model == "gpt-4o"


def test_resolve_slot_inherits_model_defaults():
    # maxTokens/topP/seed 없음 → config.yaml 모델 기본값 상속
    slot = {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0}
    settings, policy = compile_mod._settings_from_slot(slot)
    assert settings.max_tokens == 4096  # config.yaml 상속
    assert settings.top_p is None  # config에도 없음 → None
    assert settings.seed is None
    assert policy.retry_count == compile_mod.config.LLM_RETRY_COUNT


def test_resolve_default_inherits_max_tokens():
    cfg = {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0.0}
    settings, policy = compile_mod._settings_from_default(cfg)
    assert settings.max_tokens == 4096
    assert policy.fallback is None


def test_resolve_slot_zero_retry_is_preserved():
    # 0은 유효값 — None이 아니므로 전역 기본값으로 덮어씌워지지 않는다
    slot = {"provider": "google", "model": "gemini-3.1-flash-lite", "retryCount": 0}
    _settings, policy = compile_mod._settings_from_slot(slot)
    assert policy.retry_count == 0


def test_call_policy_dataclass_defaults():
    p = CallPolicy()
    assert p.timeout_seconds is None
    assert p.retry_count == 0
    assert p.fallback is None
