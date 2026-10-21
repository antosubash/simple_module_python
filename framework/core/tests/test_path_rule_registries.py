"""Most-specific-wins matching for the CORS and rate-limit registries."""

from __future__ import annotations

import logging

import pytest
from simple_module_core.cors import CorsPolicy, CorsPolicyRegistry
from simple_module_core.rate_limit import RateLimitError, RateLimitRegistry, RateLimitRule


def _p(origin: str) -> CorsPolicy:
    return CorsPolicy(origins=(origin,))


def test_exact_beats_regex_beats_longest_prefix() -> None:
    reg = CorsPolicyRegistry()
    reg.add_prefix("/api/", _p("short"))
    reg.add_prefix("/api/files/", _p("long"))
    reg.add_regex(r"/api/files/\d+$", _p("regex"))
    reg.add_exact("/api/files/7", _p("exact"))
    assert reg.match("GET", "/api/files/7").origins == ("exact",)
    assert reg.match("GET", "/api/files/8").origins == ("regex",)
    assert reg.match("GET", "/api/files/x").origins == ("long",)
    assert reg.match("GET", "/api/other").origins == ("short",)
    assert reg.match("GET", "/nope") is None


def test_order_does_not_matter_for_specificity() -> None:
    reg = CorsPolicyRegistry()
    reg.add_exact("/a/b", _p("exact"))
    reg.add_prefix("/a/", _p("prefix"))
    assert reg.match("GET", "/a/b").origins == ("exact",)


def test_tie_keeps_first_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    reg = CorsPolicyRegistry()
    reg.add_prefix("/x/", _p("first"))
    with caplog.at_level(logging.WARNING):
        reg.add_prefix("/x/", _p("second"))
    assert reg.match("GET", "/x/y").origins == ("first",)
    assert "Duplicate" in caplog.text


def test_disabled_entry_is_skipped() -> None:
    reg = CorsPolicyRegistry()
    reg.add_prefix("/a/", _p("base"))
    reg.add_exact("/a/b", _p("off"), enabled=lambda: False)
    assert reg.match("GET", "/a/b").origins == ("base",)


def test_wildcard_with_credentials_rejected() -> None:
    with pytest.raises(ValueError):
        CorsPolicy(origins=("*",), allow_credentials=True)


def test_rate_rules_are_method_aware() -> None:
    reg = RateLimitRegistry()
    post = RateLimitRule("5/minute", methods=frozenset({"post"}))
    any_ = RateLimitRule("100/minute")
    reg.add_prefix("/api/orders", any_)
    reg.add_exact("/api/orders", post)
    assert reg.match("POST", "/api/orders") is post
    assert reg.match("GET", "/api/orders") is any_
    assert post.methods == frozenset({"POST"})


def test_rate_rule_rejects_disabled_rate() -> None:
    with pytest.raises(RateLimitError):
        RateLimitRule("off")
