"""Provider chain configuration (no network)."""

import pytest
from newscrawl_api.config import Settings
from newscrawl_processor.llm.providers import (
    GeminiProvider,
    OllamaProvider,
    build_provider_chain,
    provider_is_configured,
)


def test_provider_is_configured_requires_credentials() -> None:
    settings = Settings(
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        ollama_base_url="",
    )
    assert not provider_is_configured("gemini", settings)
    assert not provider_is_configured("openai", settings)
    assert not provider_is_configured("anthropic", settings)
    assert not provider_is_configured("ollama", settings)

    settings = Settings(gemini_api_key="k", ollama_base_url="http://ollama:11434")
    assert provider_is_configured("gemini", settings)
    assert provider_is_configured("ollama", settings)


def test_local_only_chain_skips_empty_cloud_keys() -> None:
    settings = Settings(
        llm_provider="ollama",
        llm_fallback_providers="gemini",
        gemini_api_key="",
        ollama_base_url="http://ollama:11434",
        ollama_model="qwen2.5:1.5b",
    )
    chain = build_provider_chain(settings)
    assert len(chain) == 1
    assert isinstance(chain[0], OllamaProvider)
    assert chain[0].model == "qwen2.5:1.5b"


def test_hybrid_chain_gemini_then_ollama() -> None:
    settings = Settings(
        llm_provider="gemini",
        llm_fallback_providers="ollama",
        gemini_api_key="test-key",
        ollama_base_url="http://ollama:11434",
        ollama_model="qwen2.5:1.5b",
    )
    chain = build_provider_chain(settings)
    assert [p.name for p in chain] == ["gemini", "ollama"]
    assert isinstance(chain[0], GeminiProvider)
    assert isinstance(chain[1], OllamaProvider)


def test_empty_chain_raises() -> None:
    settings = Settings(
        llm_provider="gemini",
        llm_fallback_providers="",
        gemini_api_key="",
        ollama_base_url="",
    )
    with pytest.raises(ValueError, match="No configured LLM providers"):
        build_provider_chain(settings)
