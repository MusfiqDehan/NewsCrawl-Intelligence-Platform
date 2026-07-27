"""Per-source CSS selector sets.

Selector sets are DB-driven — an operator sets them on the `sources` row
(via the admin API) and they arrive here as part of the `SourceConfig`
snapshot passed to each spider. Selectors are tuples tried in order.
"""

from dataclasses import dataclass

from newscrawl_contracts import SelectorSetConfig


@dataclass(frozen=True)
class SelectorSet:
    title: tuple[str, ...] = ("h1::text",)
    subtitle: tuple[str, ...] = ()
    author: tuple[str, ...] = ()
    published_at: tuple[str, ...] = ("time::attr(datetime)",)
    category: tuple[str, ...] = ()
    # Each body selector must match paragraph-level containers.
    body: tuple[str, ...] = ("article p",)
    images: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    # CSS that must match for the page to count as "fully rendered" —
    # used by the browser-needed detection (Playwright fallback).
    body_probe: str | None = None


def build_selector_set(config: SelectorSetConfig | None) -> SelectorSet:
    """Convert a source's DB-provided selector config into a SelectorSet.

    None means the source has never had selectors configured — falls back to
    the generic defaults above rather than extracting nothing.
    """
    if config is None:
        return SelectorSet()
    return SelectorSet(
        title=tuple(config.title),
        subtitle=tuple(config.subtitle),
        author=tuple(config.author),
        published_at=tuple(config.published_at),
        category=tuple(config.category),
        body=tuple(config.body),
        images=tuple(config.images),
        tags=tuple(config.tags),
        body_probe=config.body_probe,
    )
