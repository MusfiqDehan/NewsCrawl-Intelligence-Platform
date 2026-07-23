"""LLM provider abstraction.

Gemini is the default (google-genai SDK); OpenAI, Anthropic, and Ollama are
implemented over their stable REST APIs with httpx — no extra SDK per vendor.
Every provider returns the same LLMCompletion so the extractor is
provider-agnostic, and a fallback chain is just a list of providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from newscrawl_api.config import Settings


class LLMProviderError(RuntimeError):
    """Transport/API failure — retryable, and grounds for provider fallback."""


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str


# USD per 1M tokens (prompt, completion). Operators should keep this aligned
# with vendor pricing; unknown models cost 0 so tracking never blocks work.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gpt-5.2-mini": (0.25, 2.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}


def completion_cost_usd(completion: LLMCompletion) -> float:
    prompt_rate, completion_rate = PRICING_PER_MTOK.get(completion.model, (0.0, 0.0))
    return (
        completion.prompt_tokens * prompt_rate + completion.completion_tokens * completion_rate
    ) / 1_000_000


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def complete(self, system: str, user: str) -> LLMCompletion:
        """One JSON-mode completion. Raises LLMProviderError on API failure."""

    async def aclose(self) -> None:  # pragma: no cover - trivial default
        return


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 60.0) -> None:
        from google import genai

        self.model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options={"timeout": int(timeout_seconds * 1000)},
        )

    async def complete(self, system: str, user: str) -> LLMCompletion:
        from google.genai import errors, types

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except errors.APIError as exc:
            raise LLMProviderError(f"gemini: {exc}") from exc
        usage = response.usage_metadata
        return LLMCompletion(
            text=response.text or "",
            prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
            completion_tokens=(usage.candidates_token_count or 0) if usage else 0,
            provider=self.name,
            model=self.model,
        )


class _HttpProvider(LLMProvider):
    """Shared httpx plumbing for the REST providers."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def _post(
        self, path: str, *, json: dict[str, object], headers: dict[str, str]
    ) -> dict[str, Any]:
        try:
            response = await self._http.post(path, json=json, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"{self.name}: {exc}") from exc
        data: dict[str, Any] = response.json()
        return data

    async def aclose(self) -> None:
        await self._http.aclose()


class OpenAIProvider(_HttpProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        base_url: str = "https://api.openai.com",
    ) -> None:
        super().__init__(base_url, timeout_seconds)
        self.model = model
        self._api_key = api_key

    async def complete(self, system: str, user: str) -> LLMCompletion:
        data = await self._post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        usage = data.get("usage", {})
        return LLMCompletion(
            text=data["choices"][0]["message"]["content"],
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            provider=self.name,
            model=self.model,
        )


class AnthropicProvider(_HttpProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        super().__init__(base_url, timeout_seconds)
        self.model = model
        self._api_key = api_key

    async def complete(self, system: str, user: str) -> LLMCompletion:
        data = await self._post(
            "/v1/messages",
            json={
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": 0.1,
            },
            headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
        )
        usage = data.get("usage", {})
        return LLMCompletion(
            text="".join(block.get("text", "") for block in data.get("content", [])),
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
            provider=self.name,
            model=self.model,
        )


class OllamaProvider(_HttpProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 120.0) -> None:
        super().__init__(base_url, timeout_seconds)
        self.model = model

    async def complete(self, system: str, user: str) -> LLMCompletion:
        data = await self._post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1},
            },
            headers={},
        )
        return LLMCompletion(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
            provider=self.name,
            model=self.model,
        )


def build_provider(name: str, settings: Settings) -> LLMProvider:
    timeout = settings.llm_timeout_seconds
    if name == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model, timeout)
    if name == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model, timeout)
    if name == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model, timeout)
    if name == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model, timeout)
    raise ValueError(f"Unknown LLM provider: {name!r}")


def build_provider_chain(settings: Settings) -> list[LLMProvider]:
    """Primary provider followed by the configured fallbacks, deduplicated."""
    names = [settings.llm_provider]
    names += [n.strip() for n in settings.llm_fallback_providers.split(",") if n.strip()]
    seen: set[str] = set()
    chain: list[LLMProvider] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            chain.append(build_provider(name, settings))
    return chain
