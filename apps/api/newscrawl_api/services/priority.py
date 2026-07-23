"""URL priority scoring.

priority_score = source_weight + content_type_weight + freshness_score
                 + update_frequency_score - depth_penalty

Higher scores are claimed first. Weights are configurable so operators can
re-tune scheduling behaviour without code changes.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from newscrawl_contracts.enums import UrlType

DEFAULT_TYPE_WEIGHTS: dict[UrlType, float] = {
    UrlType.HOMEPAGE: 8.0,
    UrlType.RSS: 7.0,
    UrlType.SITEMAP: 6.0,
    UrlType.ARTICLE: 5.0,
    UrlType.SECTION: 3.0,
    UrlType.OTHER: 0.5,
}


@dataclass(frozen=True)
class PriorityConfig:
    type_weights: dict[UrlType, float] = field(default_factory=lambda: dict(DEFAULT_TYPE_WEIGHTS))
    source_weight_multiplier: float = 2.0
    # Fresh articles matter most; the boost decays linearly to zero over the window.
    freshness_window_hours: float = 48.0
    freshness_max_boost: float = 4.0
    # Pages observed to change often get re-crawled sooner.
    update_frequency_max_boost: float = 2.0
    depth_penalty_per_level: float = 0.5
    max_depth_penalty: float = 3.0
    breaking_news_boost: float = 10.0


def compute_priority(
    *,
    source_weight: float,
    url_type: UrlType,
    depth: int = 0,
    published_at: datetime | None = None,
    change_rate: float | None = None,
    is_breaking: bool = False,
    now: datetime | None = None,
    config: PriorityConfig | None = None,
) -> float:
    """Compute a claim priority for a frontier URL.

    change_rate: observed fraction of recrawls where content changed (0..1).
    """
    cfg = config or PriorityConfig()
    now = now or datetime.now(UTC)

    score = source_weight * cfg.source_weight_multiplier
    score += cfg.type_weights.get(url_type, 0.5)

    if published_at is not None:
        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        if age_hours < cfg.freshness_window_hours:
            score += cfg.freshness_max_boost * (1 - age_hours / cfg.freshness_window_hours)

    if change_rate is not None:
        score += cfg.update_frequency_max_boost * min(max(change_rate, 0.0), 1.0)

    score -= min(depth * cfg.depth_penalty_per_level, cfg.max_depth_penalty)

    if is_breaking:
        score += cfg.breaking_news_boost

    return round(score, 4)
