"""LLM extractor: JSON recovery, retries, fallback, cost tracking (no network)."""

import json

import pytest
from newscrawl_processor.llm.extractor import (
    ExtractionFailedError,
    LlmExtractor,
    MalformedResponseError,
    recover_json,
)
from newscrawl_processor.llm.providers import (
    LLMCompletion,
    LLMProvider,
    LLMProviderError,
    completion_cost_usd,
)
from newscrawl_processor.llm.schema import ArticleAnalysis

VALID_ANALYSIS = {
    "summary": "The government announced a new policy affecting several sectors.",
    "topics": ["economy", "policy"],
    "entities": [{"name": "Ministry of Finance", "type": "organization"}],
    "sentiment": "neutral",
    "event_type": "policy announcement",
    "political_category": "governance",
    "keywords": ["policy", "economy"],
}


class FakeProvider(LLMProvider):
    """Scripted provider: each call pops the next behavior."""

    name = "fake"
    model = "fake-model"

    def __init__(self, script: list[str | Exception]) -> None:
        self.script = list(script)
        self.calls: list[str] = []

    async def complete(self, system: str, user: str) -> LLMCompletion:
        self.calls.append(user)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return LLMCompletion(
            text=step, prompt_tokens=100, completion_tokens=50, provider=self.name, model=self.model
        )


def extractor(*providers: LLMProvider) -> LlmExtractor:
    return LlmExtractor(list(providers), max_retries=2, backoff_base_seconds=0.001)


async def analyze(ex: LlmExtractor) -> tuple[ArticleAnalysis, object]:
    return await ex.analyze(title="Policy announced", body="Body " * 100, language="en")


class TestRecoverJson:
    def test_plain_json(self) -> None:
        assert recover_json(json.dumps(VALID_ANALYSIS))["sentiment"] == "neutral"

    def test_markdown_fences_stripped(self) -> None:
        fenced = f"```json\n{json.dumps(VALID_ANALYSIS)}\n```"
        assert recover_json(fenced)["summary"] == VALID_ANALYSIS["summary"]

    def test_prose_padding_stripped(self) -> None:
        padded = f"Here is the analysis:\n{json.dumps(VALID_ANALYSIS)}\nHope this helps!"
        assert recover_json(padded)["topics"] == ["economy", "policy"]

    def test_garbage_raises(self) -> None:
        with pytest.raises(MalformedResponseError):
            recover_json("I cannot analyze this article.")

    def test_json_array_rejected(self) -> None:
        with pytest.raises(MalformedResponseError):
            recover_json("[1, 2, 3]")


class TestExtractor:
    async def test_success_first_try(self) -> None:
        provider = FakeProvider([json.dumps(VALID_ANALYSIS)])
        analysis, usage = await analyze(extractor(provider))
        assert analysis.sentiment == "neutral"
        assert analysis.entities[0].name == "Ministry of Finance"
        assert usage.attempts == 1  # type: ignore[attr-defined]
        assert usage.total_tokens == 150  # type: ignore[attr-defined]

    async def test_malformed_then_valid_with_corrective_note(self) -> None:
        provider = FakeProvider(["not json at all", json.dumps(VALID_ANALYSIS)])
        analysis, usage = await analyze(extractor(provider))
        assert analysis.summary == VALID_ANALYSIS["summary"]
        assert usage.attempts == 2  # type: ignore[attr-defined]
        # Second call got the corrective instruction appended
        assert "ONLY one JSON object" in provider.calls[1]
        # Both attempts' tokens are accounted
        assert usage.total_tokens == 300  # type: ignore[attr-defined]

    async def test_schema_violation_retried(self) -> None:
        bad = dict(VALID_ANALYSIS, sentiment="angry")  # not in the Literal
        provider = FakeProvider([json.dumps(bad), json.dumps(VALID_ANALYSIS)])
        analysis, _ = await analyze(extractor(provider))
        assert analysis.sentiment == "neutral"

    async def test_hallucinated_fields_stripped(self) -> None:
        bad = dict(VALID_ANALYSIS, invented_field="x")
        provider = FakeProvider([json.dumps(bad)])
        analysis, usage = await analyze(extractor(provider))
        assert analysis.sentiment == "neutral"
        assert usage.attempts == 1  # type: ignore[attr-defined]

    async def test_provider_error_falls_back_to_next_provider(self) -> None:
        primary = FakeProvider([LLMProviderError("boom"), LLMProviderError("boom")])
        secondary = FakeProvider([json.dumps(VALID_ANALYSIS)])
        analysis, usage = await analyze(extractor(primary, secondary))
        assert analysis.sentiment == "neutral"
        assert usage.provider == "fake"  # type: ignore[attr-defined]
        assert usage.attempts == 3  # type: ignore[attr-defined]

    async def test_non_retryable_error_skips_to_next_provider(self) -> None:
        """429 / quota errors must not burn retries before falling back to Ollama."""
        primary = FakeProvider(
            [LLMProviderError("gemini: 429 RESOURCE_EXHAUSTED", retryable=False)]
        )
        secondary = FakeProvider([json.dumps(VALID_ANALYSIS)])
        analysis, usage = await analyze(extractor(primary, secondary))
        assert analysis.sentiment == "neutral"
        assert usage.attempts == 2  # type: ignore[attr-defined]
        assert len(primary.calls) == 1

    async def test_all_providers_exhausted_raises_with_usage(self) -> None:
        primary = FakeProvider([LLMProviderError("a"), LLMProviderError("b")])
        secondary = FakeProvider(["garbage", "more garbage"])
        with pytest.raises(ExtractionFailedError) as exc_info:
            await analyze(extractor(primary, secondary))
        usage = exc_info.value.usage
        assert usage.attempts == 4
        # Malformed attempts still consumed tokens
        assert usage.total_tokens == 300
        assert len(usage.errors) == 4

    async def test_requires_at_least_one_provider(self) -> None:
        with pytest.raises(ValueError, match="provider"):
            LlmExtractor([])


class TestCostTracking:
    def test_known_model_pricing(self) -> None:
        completion = LLMCompletion(
            text="{}",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            provider="gemini",
            model="gemini-2.5-flash",
        )
        assert completion_cost_usd(completion) == pytest.approx(0.30 + 2.50)

    def test_unknown_model_costs_zero(self) -> None:
        completion = LLMCompletion(
            text="{}",
            prompt_tokens=1000,
            completion_tokens=1000,
            provider="ollama",
            model="qwen2.5:1.5b",
        )
        assert completion_cost_usd(completion) == 0.0
