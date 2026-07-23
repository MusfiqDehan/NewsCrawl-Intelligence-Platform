"""Strict schema for LLM article analysis output.

The LLM's JSON is untrusted input: everything is validated against this model
before touching the database, with `extra="forbid"` so hallucinated fields
fail loudly instead of silently passing through.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sentiment = Literal["positive", "negative", "neutral", "mixed"]
EntityTypeName = Literal["person", "organization", "location", "event", "other"]


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    type: EntityTypeName


class ArticleAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=10, max_length=2000)
    topics: list[str] = Field(default_factory=list, max_length=10)
    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=50)
    sentiment: Sentiment = "neutral"
    event_type: str | None = Field(default=None, max_length=100)
    political_category: str | None = Field(default=None, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("topics", "keywords")
    @classmethod
    def _strip_and_drop_empty(cls, values: list[str]) -> list[str]:
        return [v.strip() for v in values if v and v.strip()]


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
