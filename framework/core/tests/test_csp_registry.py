"""Modules can extend the host Content-Security-Policy with extra origins.

Found in the field: the pagebuilder module's editor loads a stylesheet from
``rsms.me``, which the framework CSP blocks — and there was no way for the
module (or the host) to declare that origin short of patching the installed
package. ``register_csp_sources`` closes that gap the same way
``register_public_routes`` does for auth exemptions.
"""

from __future__ import annotations

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.csp import CspSourceError, CspSourceRegistry

_POLICY = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:"
)


class TestRegistry:
    def test_extends_existing_directive(self) -> None:
        reg = CspSourceRegistry()
        reg.add("style-src", "https://rsms.me")
        out = reg.extend_policy(_POLICY)
        assert (
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://rsms.me" in out
        )

    def test_duplicate_and_already_present_sources_are_not_repeated(self) -> None:
        reg = CspSourceRegistry()
        reg.add("style-src", "https://rsms.me")
        reg.add("style-src", "https://rsms.me")
        reg.add("style-src", "https://fonts.googleapis.com")  # already in the policy
        out = reg.extend_policy(_POLICY)
        assert out.count("https://rsms.me") == 1
        assert out.count("https://fonts.googleapis.com") == 1

    def test_missing_directive_gets_self_plus_source(self) -> None:
        """A brand-new clause must keep 'self', or it would *narrow* the policy:
        without the clause the browser falls back to default-src 'self'."""
        reg = CspSourceRegistry()
        reg.add("connect-src", "https://api.example.com")
        out = reg.extend_policy(_POLICY)
        assert "connect-src 'self' https://api.example.com" in out

    def test_missing_elem_directive_inherits_its_fallback_clause(self) -> None:
        """style-src-elem falls back to style-src (not default-src): a fresh
        clause must inherit style-src's sources, or creating it would silently
        drop 'unsafe-inline' and the font origins from element styles."""
        reg = CspSourceRegistry()
        reg.add("style-src-elem", "https://rsms.me")
        out = reg.extend_policy(_POLICY)
        assert (
            "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com https://rsms.me"
            in out
        )

    def test_empty_registry_returns_policy_unchanged(self) -> None:
        reg = CspSourceRegistry()
        assert reg.extend_policy(_POLICY) == _POLICY
        assert not reg

    def test_unknown_directive_rejected(self) -> None:
        reg = CspSourceRegistry()
        with pytest.raises(CspSourceError, match="directive"):
            reg.add("script-src-attr; evil", "https://x.example")

    def test_injection_shaped_sources_rejected(self) -> None:
        reg = CspSourceRegistry()
        for bad in (
            "https://x; script-src *",
            "https://x 'unsafe-eval'",
            "",
            "'*'",
            "https://a.example,https://b.example",  # comma would smuggle a 2nd policy
            "*.",  # wildcard with no host
        ):
            with pytest.raises(CspSourceError):
                reg.add("style-src", bad)

    def test_base_directive_extras_reach_existing_elem_clause(self) -> None:
        """`script-src-elem` shadows `script-src` once present: without the
        mirror, a module's script-src origin never reaches <script> elements —
        the very load it declared the origin for."""
        reg = CspSourceRegistry()
        reg.add("script-src", "https://cdn.example.com")
        policy = "default-src 'self'; script-src 'self'; script-src-elem 'self' 'unsafe-inline'"
        out = reg.extend_policy(policy)
        assert "script-src 'self' https://cdn.example.com" in out
        assert "script-src-elem 'self' 'unsafe-inline' https://cdn.example.com" in out


class TestHook:
    def test_register_csp_sources_is_a_noop_by_default(self) -> None:
        class Quiet(ModuleBase):
            meta = ModuleMeta(name="Quiet")

        reg = CspSourceRegistry()
        Quiet().register_csp_sources(reg)
        assert not reg
