"""Deterministic, configurable URL normalization.

The normalized URL is the platform-wide deduplication key: the same logical
page must always normalize to the same string, so every step here is
deterministic and order-independent.

Pipeline:
  1. resolve relative URLs against a base
  2. lowercase scheme and hostname
  3. remove default ports (80/443)
  4. remove fragments (configurable)
  5. remove tracking query parameters (configurable per source)
  6. sort remaining query parameters (safe: order is semantically irrelevant
     for the query-string parameter model news sites use)
  7. normalize percent-encoding
  8. normalize trailing slash (strip except for root path)
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from w3lib.url import canonicalize_url

# Parameters that never change page content — safe to strip everywhere.
DEFAULT_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "gbraid",
        "wbraid",
        "fbclid",
        "msclkid",
        "twclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "cmpid",
        "ncid",
        "ocid",
        "at_medium",
        "at_campaign",
        "xtor",
    }
)

ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


@dataclass(frozen=True)
class NormalizationConfig:
    """Per-source overrides live in sources.url_normalization (JSONB)."""

    remove_tracking_params: bool = True
    extra_tracking_params: frozenset[str] = field(default_factory=frozenset)
    # If non-empty, ONLY these query parameters are kept (whitelist mode).
    keep_params: frozenset[str] = field(default_factory=frozenset)
    strip_all_params: bool = False
    keep_fragment: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> NormalizationConfig:
        if not raw:
            return cls()
        return cls(
            remove_tracking_params=bool(raw.get("remove_tracking_params", True)),
            extra_tracking_params=frozenset(raw.get("extra_tracking_params", ())),
            keep_params=frozenset(raw.get("keep_params", ())),
            strip_all_params=bool(raw.get("strip_all_params", False)),
            keep_fragment=bool(raw.get("keep_fragment", False)),
        )


class UrlNormalizationError(ValueError):
    """URL cannot be normalized (bad scheme, no host, malformed)."""


def normalize_url(
    url: str,
    *,
    base_url: str | None = None,
    config: NormalizationConfig | None = None,
) -> str:
    cfg = config or NormalizationConfig()

    candidate = url.strip()
    if base_url:
        candidate = urljoin(base_url, candidate)

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise UrlNormalizationError(f"Malformed URL: {url!r}") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlNormalizationError(f"Unsupported scheme {scheme!r} in {url!r}")
    if not parts.hostname:
        raise UrlNormalizationError(f"URL has no host: {url!r}")

    # Host: lowercase; strip default port; keep explicit non-default ports.
    host = parts.hostname.lower()
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    # Query parameters
    query = ""
    if not cfg.strip_all_params and parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if cfg.keep_params:
            pairs = [(k, v) for k, v in pairs if k in cfg.keep_params]
        elif cfg.remove_tracking_params:
            blocked = DEFAULT_TRACKING_PARAMS | cfg.extra_tracking_params
            pairs = [(k, v) for k, v in pairs if k.lower() not in blocked]
        pairs.sort()
        query = urlencode(pairs)

    fragment = parts.fragment if cfg.keep_fragment else ""

    # Trailing slash: strip except for the root path.
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    rebuilt = urlunsplit((scheme, host, path, query, fragment))
    # w3lib canonicalize_url normalizes percent-encoding and idempotently
    # re-sorts the query; keep_fragments preserves our fragment decision.
    return canonicalize_url(rebuilt, keep_fragments=cfg.keep_fragment)


def url_hash(normalized_url: str) -> str:
    """sha256 hex digest of the normalized URL — the frontier dedup key."""
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def url_domain(normalized_url: str) -> str:
    """Host (without port) used for per-domain politeness."""
    host = urlsplit(normalized_url).hostname
    if not host:
        raise UrlNormalizationError(f"URL has no host: {normalized_url!r}")
    return host
