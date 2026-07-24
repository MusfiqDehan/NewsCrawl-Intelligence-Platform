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

MAX_BODY_CHARS = 1_200
# Tiny local models choke on long prompt+body; keep Ollama prompts short.
MAX_BODY_CHARS_LOCAL = 600

SYSTEM_PROMPT = (
    "You are a news analysis engine. You receive one news article (Bangla or "
    "English) and return ONLY a single JSON object matching exactly this "
    "schema, with no markdown fences and no commentary:\n"
    f"{analysis_json_schema()}\n"
    "Required keys (use exactly these names): summary, topics, entities, "
    "sentiment, event_type, political_category, keywords.\n"
    "Example (structure only):\n"
    '{"summary":"Officials announced a new policy after talks in Dhaka.",'
    '"topics":["policy","government"],'
    '"entities":[{"name":"Dhaka","type":"location"}],'
    '"sentiment":"neutral","event_type":"policy announcement",'
    '"political_category":"governance","keywords":["policy","Dhaka"]}\n'
    "Write the summary in the same language as the article. Use null (not "
    "empty strings) for event_type/political_category when not applicable."
)

# Compact prompt for CPU/local models — long schemas make prompt-eval dominate.
LOCAL_SYSTEM_PROMPT = (
    "Analyze one news article. Reply with ONLY a JSON object using exactly "
    "these keys: summary, topics, entities, sentiment, event_type, "
    "political_category, keywords.\n"
    "summary = 2-4 sentences in the article language; "
    "topics = up to 8 short phrases; "
    'entities = [{"name":"...","type":"person|organization|location|event|other"}]; '
    "sentiment = positive|negative|neutral|mixed; "
    "event_type and political_category = short label or null; "
    "keywords = up to 12 words. No markdown, no extra keys."
)

_CORRECTIVE_NOTE = (
    "\n\nIMPORTANT: your previous reply was not valid JSON for the schema. "
    "Reply with ONLY one JSON object using exactly these keys: summary, "
    "topics, entities, sentiment, event_type, political_category, keywords. "
    "No other keys. No code fences. No explanations."
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
    # Small local models often invent extra keys; drop unknowns before validation.
    allowed = set(ArticleAnalysis.model_fields)
    return {key: value for key, value in parsed.items() if key in allowed}


def build_user_prompt(title: str, body: str, language: str, *, max_body_chars: int = MAX_BODY_CHARS) -> str:
    truncated = body[:max_body_chars]
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

        for provider in self.providers:
            max_chars = MAX_BODY_CHARS_LOCAL if provider.name == "ollama" else MAX_BODY_CHARS
            user_prompt = build_user_prompt(title, body, language, max_body_chars=max_chars)
            prompt = user_prompt
            system = LOCAL_SYSTEM_PROMPT if provider.name == "ollama" else SYSTEM_PROMPT
            # When Ollama is only a fallback, don't burn minutes of CPU retries.
            provider_retries = (
                1 if provider.name == "ollama" and len(self.providers) > 1 else self.max_retries
            )
            for attempt in range(1, provider_retries + 1):
                usage.attempts += 1
                try:
                    completion = await provider.complete(system, prompt)
                except LLMProviderError as exc:
                    usage.errors.append(str(exc))
                    log.warning(
                        "llm_provider_error",
                        provider=provider.name,
                        attempt=attempt,
                        retryable=exc.retryable,
                        error=str(exc),
                    )
                    # Quota/auth failures (e.g. Gemini 429) → next provider immediately.
                    if not getattr(exc, "retryable", True):
                        break
                    if attempt < provider_retries:
                        await asyncio.sleep(self.backoff_base_seconds * 2 ** (attempt - 1))
                    continue

                usage.add(completion)
                raw_text = (completion.text or "").strip()
                if not raw_text or raw_text in {"{}", "null", "[]"}:
                    usage.errors.append("malformed: empty JSON reply")
                    log.warning(
                        "llm_malformed_response",
                        provider=provider.name,
                        attempt=attempt,
                        error="empty JSON reply",
                    )
                    prompt = user_prompt + _CORRECTIVE_NOTE
                    continue
                try:
                    analysis = ArticleAnalysis.model_validate(recover_json(raw_text))
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
