"""Strict schema for LLM article analysis output.

The LLM's JSON is untrusted input: everything is validated against this model
before touching the database, with `extra="forbid"` so hallucinated fields
fail loudly instead of silently passing through.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.aliases import AliasChoices

Sentiment = Literal["positive", "negative", "neutral", "mixed"]
EntityTypeName = Literal["person", "organization", "location", "event", "other"]


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("name", "entity"),
    )
    type: EntityTypeName

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ArticleAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=10, max_length=2000)
    topics: list[str] = Field(default_factory=list, max_length=10)
    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=50)
    sentiment: Sentiment = "neutral"
    event_type: str | None = Field(default=None, max_length=100)
    political_category: str | None = Field(default=None, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("sentiment", mode="before")
    @classmethod
    def _normalize_sentiment(cls, value: object) -> object:
        if value is None or value == "":
            return "neutral"
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("entities", mode="before")
    @classmethod
    def _normalize_entities(cls, values: object) -> object:
        # Small local models sometimes emit {"Dhaka": "location"} instead of a list.
        if isinstance(values, dict):
            converted: list[dict[str, str]] = []
            for key, val in values.items():
                if isinstance(val, dict):
                    converted.append(val)
                elif isinstance(val, str):
                    lowered = val.strip().lower()
                    if lowered in {"person", "organization", "location", "event", "other"}:
                        converted.append({"name": str(key), "type": lowered})
                    else:
                        converted.append({"name": val.strip() or str(key), "type": "other"})
            return converted
        return values

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        cleaned = [str(v).strip() for v in values if v and str(v).strip()]
        return cleaned[:10]

    @field_validator("keywords", mode="before")
    @classmethod
    def _normalize_keywords(cls, values: object) -> list[str]:
        # Gemini often returns one extra keyword; truncate instead of failing the
        # whole extraction (which stalled the LLM queue behind retries).
        if not isinstance(values, list):
            return []
        cleaned = [str(v).strip() for v in values if v and str(v).strip()]
        return cleaned[:15]


def analysis_json_schema() -> str:
    """Compact schema description embedded in the prompt."""
    return (
        "{\n"
        '  "summary": "2-4 sentence summary in the article\'s own language",\n'
        '  "topics": ["up to 10 topical phrases"],\n'
        '  "entities": [{"name": "...", "type": '
        '"person|organization|location|event|other"}],\n'
        '  "sentiment": "positive|negative|neutral|mixed",\n'
        '  "event_type": "short event label (e.g. election, disaster, protest) or null",\n'
        '  "political_category": "short label or null for non-political articles",\n'
        '  "keywords": ["up to 15 keywords"]\n'
        "}"
    )
