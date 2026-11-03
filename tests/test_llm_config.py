"""Testes da configuração do modelo (sem chamadas de rede)."""

from __future__ import annotations

import pytest

from emporio.config import DEFAULT_MODEL, OPENROUTER_BASE_URL, Settings
from emporio.llm import LLMConfigError, build_chat_model, describe


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLM_API_KEY", "OPENROUTER_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                "LLM_FAST_MODEL", "LLM_FALLBACK_MODELS"):
        monkeypatch.delenv(var, raising=False)


def make_settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_defaults_point_to_openrouter_preset() -> None:
    s = make_settings()
    assert s.llm_base_url == OPENROUTER_BASE_URL
    assert s.llm_model == DEFAULT_MODEL == "@preset/emporio-agent"
    assert s.is_openrouter


def test_model_can_be_changed_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    s = Settings(_env_file=None)
    assert s.llm_model == "openai/gpt-4o-mini"
    assert s.llm_api_key.get_secret_value() == "sk-or-test"


def test_missing_key_raises_clear_error() -> None:
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        build_chat_model(make_settings())


def test_openrouter_client_with_fallbacks() -> None:
    s = make_settings(
        llm_api_key="sk-or-test",
        llm_model="anthropic/claude-sonnet-4.5",
        llm_fallback_models="openai/gpt-4o-mini, google/gemini-2.5-flash",
    )
    model = build_chat_model(s)
    assert model.model_name == "anthropic/claude-sonnet-4.5"
    assert model.openai_api_base == OPENROUTER_BASE_URL
    assert model.extra_body == {
        "models": ["anthropic/claude-sonnet-4.5", "openai/gpt-4o-mini", "google/gemini-2.5-flash"]
    }
    assert "X-Title" in model.default_headers


def test_fast_role_uses_fast_model() -> None:
    s = make_settings(llm_api_key="k", llm_fast_model="openai/gpt-4o-mini")
    assert build_chat_model(s, role="fast").model_name == "openai/gpt-4o-mini"
    assert build_chat_model(make_settings(llm_api_key="k"), role="fast").model_name == DEFAULT_MODEL


def test_local_provider_without_key() -> None:
    s = make_settings(llm_base_url="http://localhost:11434/v1", llm_model="llama3.1")
    model = build_chat_model(s)
    assert model.model_name == "llama3.1"
    assert not model.extra_body  # parâmetros do OpenRouter não vazam para outros provedores


def test_describe_masks_api_key() -> None:
    text = describe(make_settings(llm_api_key="sk-or-v1-abcdefghijklmnop"))
    assert "abcdefghijklmnop" not in text
    assert "sk-or-" in text
