import pytest
from newscrawl_crawler_utils.urlnorm import (
    NormalizationConfig,
    UrlNormalizationError,
    normalize_url,
    url_domain,
    url_hash,
)


class TestSpecCases:
    """The four canonical cases from the platform specification must all
    normalize to the same URL."""

    def test_plain(self) -> None:
        assert normalize_url("https://example.com/article") == "https://example.com/article"

    def test_trailing_slash(self) -> None:
        assert normalize_url("https://example.com/article/") == "https://example.com/article"

    def test_uppercase_host_and_fragment(self) -> None:
        assert normalize_url("https://EXAMPLE.COM/article#section") == "https://example.com/article"

    def test_tracking_param(self) -> None:
        assert (
            normalize_url("https://example.com/article?utm_source=facebook")
            == "https://example.com/article"
        )

    def test_all_variants_identical_hash(self) -> None:
        variants = [
            "https://example.com/article",
            "https://example.com/article/",
            "https://EXAMPLE.COM/article#section",
            "https://example.com/article?utm_source=facebook",
        ]
        hashes = {url_hash(normalize_url(v)) for v in variants}
        assert len(hashes) == 1


class TestNormalizationRules:
    def test_default_port_removed(self) -> None:
        assert normalize_url("https://example.com:443/a") == "https://example.com/a"
        assert normalize_url("http://example.com:80/a") == "http://example.com/a"

    def test_non_default_port_kept(self) -> None:
        assert normalize_url("https://example.com:8443/a") == "https://example.com:8443/a"

    def test_root_path_slash_kept(self) -> None:
        assert normalize_url("https://example.com") == "https://example.com/"
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_query_params_sorted(self) -> None:
        assert (
            normalize_url("https://example.com/a?b=2&a=1")
            == normalize_url("https://example.com/a?a=1&b=2")
            == "https://example.com/a?a=1&b=2"
        )

    def test_meaningful_params_preserved(self) -> None:
        assert (
            normalize_url("https://example.com/news?page=2&utm_medium=social")
            == "https://example.com/news?page=2"
        )

    def test_relative_url_resolved(self) -> None:
        assert (
            normalize_url("/politics/story-1", base_url="https://example.com/section")
            == "https://example.com/politics/story-1"
        )

    def test_percent_encoding_normalized(self) -> None:
        # Same character, different encodings
        assert normalize_url("https://example.com/a%7Eb") == normalize_url(
            "https://example.com/a~b"
        )

    def test_bangla_path_preserved(self) -> None:
        # Bengali URLs must survive normalization round-trips deterministically
        url = "https://example.com/বাংলাদেশ/রাজনীতি"
        assert normalize_url(url) == normalize_url(normalize_url(url))

    def test_idempotent(self) -> None:
        urls = [
            "https://EXAMPLE.com:443/Article/?utm_source=x&b=2&a=1#frag",
            "https://example.com/a b/c",
        ]
        for url in urls:
            once = normalize_url(url)
            assert normalize_url(once) == once


class TestConfigurability:
    def test_strip_all_params(self) -> None:
        cfg = NormalizationConfig(strip_all_params=True)
        assert (
            normalize_url("https://example.com/a?id=5&x=1", config=cfg) == "https://example.com/a"
        )

    def test_keep_params_whitelist(self) -> None:
        cfg = NormalizationConfig(keep_params=frozenset({"id"}))
        assert (
            normalize_url("https://example.com/a?id=5&sort=asc", config=cfg)
            == "https://example.com/a?id=5"
        )

    def test_extra_tracking_params(self) -> None:
        cfg = NormalizationConfig(extra_tracking_params=frozenset({"session"}))
        assert (
            normalize_url("https://example.com/a?session=xyz&id=1", config=cfg)
            == "https://example.com/a?id=1"
        )

    def test_keep_fragment(self) -> None:
        cfg = NormalizationConfig(keep_fragment=True)
        assert (
            normalize_url("https://example.com/a#part2", config=cfg)
            == "https://example.com/a#part2"
        )

    def test_from_dict_roundtrip(self) -> None:
        cfg = NormalizationConfig.from_dict(
            {"strip_all_params": True, "keep_fragment": True, "keep_params": ["id"]}
        )
        assert cfg.strip_all_params is True
        assert cfg.keep_fragment is True
        assert cfg.keep_params == frozenset({"id"})

    def test_from_dict_none(self) -> None:
        assert NormalizationConfig.from_dict(None) == NormalizationConfig()


class TestRejection:
    @pytest.mark.parametrize(
        "bad", ["ftp://example.com/x", "javascript:alert(1)", "mailto:a@b.c", "not a url"]
    )
    def test_bad_schemes_rejected(self, bad: str) -> None:
        with pytest.raises(UrlNormalizationError):
            normalize_url(bad)


def test_url_domain() -> None:
    assert url_domain("https://www.example.com:8443/x") == "www.example.com"
