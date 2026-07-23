"""LLM article analysis with retries, malformed-JSON recovery, and fallback.

Failure ladder per provider:
  1. API error → exponential backoff, retry (transient failures)
  2. malformed/invalid JSON → retry with a corrective instruction appended
  3. retries exhausted → next provider in the fallback chain
  4. chain exhausted → ExtractionFailedError (caller dead-letters the message)
"""

import asyncio
import json
import re
from dataclasses import dataclass, field

from newscrawl_api.observability import get_logger
from pydantic import ValidationError

from newscrawl_processor.llm.providers import (
    LLMCompletion,
    LLMProvider,
    LLMProviderError,
    completion_cost_usd,
)
from newscrawl_processor.llm.schema import ArticleAnalysis, analysis_json_schema

log = get_logger()

MAX_BODY_CHARS = 12_000

SYSTEM_PROMPT = (
    "You are a news analysis engine. You receive one news article (Bangla or "
    "English) and return ONLY a single JSON object matching exactly this "
    "schema, with no markdown fences and no commentary:\n"
    f"{analysis_json_schema()}\n"
    "Write the summary in the same language as the article. Use null (not "
    "empty strings) for event_type/political_category when not applicable."
)

_CORRECTIVE_NOTE = (
    "\n\nIMPORTANT: your previous reply was not valid JSON for the schema. "
    "Reply with ONLY the JSON object, no code fences, no explanations."
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class ExtractionFailedError(RuntimeError):
    """All providers/retries exhausted for this article."""

    def __init__(self, message: str, usage: LlmUsage) -> None:
        super().__init__(message)
        self.usage = usage


class MalformedResponseError(ValueError):
    """Model reply was not parseable/valid against the schema."""


@dataclass
class LlmUsage:
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    attempts: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, completion: LLMCompletion) -> None:
        # Every attempt costs real tokens — account for all of them.
        self.provider = completion.provider
        self.model = completion.model
        self.prompt_tokens += completion.prompt_tokens
        self.completion_tokens += completion.completion_tokens
        self.cost_usd += completion_cost_usd(completion)


def recover_json(text: str) -> dict[str, object]:
    """Parse model output into a dict, tolerating fences and prose padding."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", candidate).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(candidate)
        if match is None:
            raise MalformedResponseError(f"No JSON object in reply: {text[:200]!r}") from None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(f"Unparseable JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MalformedResponseError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


def build_user_prompt(title: str, body: str, language: str) -> str:
    truncated = body[:MAX_BODY_CHARS]
    return f"Language: {language}\nTitle: {title}\n\nArticle:\n{truncated}"


class LlmExtractor:
    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        max_retries: int = 3,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        if not providers:
            raise ValueError("At least one LLM provider is required")
        self.providers = providers
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds

    async def analyze(
        self, *, title: str, body: str, language: str
    ) -> tuple[ArticleAnalysis, LlmUsage]:
        usage = LlmUsage()
        user_prompt = build_user_prompt(title, body, language)

        for provider in self.providers:
            prompt = user_prompt
            for attempt in range(1, self.max_retries + 1):
                usage.attempts += 1
                try:
                    completion = await provider.complete(SYSTEM_PROMPT, prompt)
                except LLMProviderError as exc:
                    usage.errors.append(str(exc))
                    log.warning(
                        "llm_provider_error",
                        provider=provider.name,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.backoff_base_seconds * 2 ** (attempt - 1))
                    continue

                usage.add(completion)
                try:
                    analysis = ArticleAnalysis.model_validate(recover_json(completion.text))
                except (MalformedResponseError, ValidationError) as exc:
                    usage.errors.append(f"malformed: {exc}")
                    log.warning(
                        "llm_malformed_response",
                        provider=provider.name,
                        attempt=attempt,
                        error=str(exc)[:300],
                    )
                    # Nudge the model instead of blindly re-sending the same prompt
                    prompt = user_prompt + _CORRECTIVE_NOTE
                    continue
                return analysis, usage

        raise ExtractionFailedError(
            f"All LLM providers failed after {usage.attempts} attempts: {usage.errors[-3:]}",
            usage,
        )
