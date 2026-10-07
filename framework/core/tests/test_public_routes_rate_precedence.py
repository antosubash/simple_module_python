"""A rate-bearing public rule is not shadowed by an earlier overlapping rule (GH #347)."""

from __future__ import annotations

from simple_module_core.public_routes import PublicRouteRegistry


def test_rate_bearing_rule_beats_earlier_overlapping_rule_without_one() -> None:
    registry = PublicRouteRegistry()
    registry.add_prefix("/api/pub/")
    registry.add_exact("/api/pub/login", rate="5/minute")
    login = registry.match("GET", "/api/pub/login")
    other = registry.match("GET", "/api/pub/other")
    assert login is not None and login.rate == "5/minute"
    assert other is not None and other.rate is None


def test_first_registered_wins_among_equals() -> None:
    registry = PublicRouteRegistry()
    registry.add_prefix("/a/", rate="1/minute")
    registry.add_prefix("/a/b", rate="9/minute")
    rule = registry.match("GET", "/a/b")
    assert rule is not None and rule.rate == "1/minute"
