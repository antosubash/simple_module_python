"""Tests for the shared redirect-target sanitiser."""

from __future__ import annotations

import pytest
from simple_module_core.redirect_safety import safe_next, safe_next_or_none


class TestSafeNext:
    @pytest.mark.parametrize(
        "raw",
        [
            "/dashboard/",
            "/admin/users?page=2",
            "/admin/users#anchor",
            "/",
        ],
    )
    def test_same_site_paths_pass_through(self, raw: str) -> None:
        assert safe_next(raw) == raw

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "https://evil.example/phish",
            "dashboard/",
            "javascript:alert(1)",
        ],
    )
    def test_non_relative_targets_are_rejected(self, raw: str | None) -> None:
        assert safe_next(raw) == "/"

    @pytest.mark.parametrize("raw", ["//evil.example", "/\\evil.example"])
    def test_off_site_lookalikes_are_rejected(self, raw: str) -> None:
        """Browsers resolve both forms against the remote host, not ours."""
        assert safe_next(raw) == "/"

    @pytest.mark.parametrize("raw", ["/ok\r\nLocation: https://evil.example", "/ok\nX: y"])
    def test_header_smuggling_is_rejected(self, raw: str) -> None:
        assert safe_next(raw) == "/"

    def test_fallback_is_configurable(self) -> None:
        assert safe_next("https://evil.example", fallback="/login") == "/login"


class TestSafeNextOrNone:
    def test_valid_target_returned(self) -> None:
        assert safe_next_or_none("/admin/settings") == "/admin/settings"

    @pytest.mark.parametrize("raw", [None, "", "//evil.example", "https://evil.example"])
    def test_unusable_target_is_none(self, raw: str | None) -> None:
        assert safe_next_or_none(raw) is None

    def test_root_is_a_real_target_not_a_miss(self) -> None:
        """``/`` must stay distinguishable from "nothing stashed" — otherwise a
        caller cannot tell whether to fall back to its configured destination."""
        assert safe_next_or_none("/") == "/"
