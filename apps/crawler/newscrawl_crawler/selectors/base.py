"""Per-source CSS selector sets.

Each source registers one SelectorSet. Selectors are tuples tried in order —
when a site tweaks its markup only its own module changes, and the fixture
contract tests for that source catch the break immediately.
"""

from dataclasses import dataclass


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


_REGISTRY: dict[str, SelectorSet] = {}


def register(slug: str, selectors: SelectorSet) -> None:
    _REGISTRY[slug] = selectors


def get_selector_set(slug: str) -> SelectorSet:
    return _REGISTRY.get(slug, SelectorSet())
