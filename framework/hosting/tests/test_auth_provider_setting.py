"""``SM_AUTH_PROVIDER`` normalisation on BootstrapSettings.

The host reads this through ``Settings``; ``make doctor`` and ``smpy host
gen-pages`` read it through ``simple_module_core.resolve_auth_provider``.
The two must agree on every input, or the tools report on a different module
set than the app boots with.
"""

from __future__ import annotations

import os

import pytest
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER, resolve_auth_provider
from simple_module_hosting.settings import Settings


def _settings(**overrides) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        **overrides,
    )


class TestAuthProviderSetting:
    @pytest.fixture(autouse=True)
    def _isolated_env(self, monkeypatch, tmp_path):
        """Run against an empty ``.env`` and a throwaway environment.

        ``Settings`` resolves ``env_file=".env"`` relative to the working
        directory, so without the chdir a developer running Keycloak locally
        would fail the default-value assertions below — the very coupling
        these tests exist to pin down.
        """
        monkeypatch.setattr(os, "environ", dict(os.environ))
        monkeypatch.delenv("SM_AUTH_PROVIDER", raising=False)
        # Settings discovers the .env via find_env_file: SM_PROJECT_ROOT
        # exported in the developer's shell would beat the chdir isolation.
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

    def test_defaults_to_users(self):
        assert _settings().auth_provider == DEFAULT_AUTH_PROVIDER

    def test_explicit_value_passes_through(self):
        assert _settings(auth_provider="keycloak").auth_provider == "keycloak"

    @pytest.mark.parametrize("raw", ["", "   ", "\t"])
    def test_blank_falls_back_to_the_default(self, raw: str):
        """``SM_AUTH_PROVIDER=`` in .env yielded '', which matches no provider."""
        assert _settings(auth_provider=raw).auth_provider == DEFAULT_AUTH_PROVIDER

    def test_surrounding_whitespace_stripped(self):
        assert _settings(auth_provider=" keycloak ").auth_provider == "keycloak"

    @pytest.mark.parametrize("raw", ["", "   ", "keycloak", " keycloak "])
    def test_agrees_with_resolve_auth_provider(self, raw: str, monkeypatch):
        """Host and out-of-process readers must land on the same name."""
        monkeypatch.setenv("SM_AUTH_PROVIDER", raw)
        assert _settings().auth_provider == resolve_auth_provider()


class TestShimKeepsItsEnvironment:
    """``Settings`` mixes ``HostSettings`` with ``BootstrapSettings``.

    Both halves namespace their env reads under ``SM_``, and the bootstrap
    half's must keep working: ``SM_DATABASE_URL`` and friends are read by
    design, before any database exists to read them from. The bare,
    unprefixed names must not resolve on either half (GH #283).
    """

    def test_bootstrap_fields_still_read_sm_prefixed_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SM_AUTH_PROVIDER", "keycloak")
        monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        settings = Settings(environment="testing", secret_key="test-secret-key")

        assert settings.auth_provider == "keycloak"
        assert settings.database_url == "sqlite+aiosqlite:///:memory:"

    def test_host_fields_stay_namespaced_on_the_shim(self, monkeypatch) -> None:
        """The bare name never works, even where the shim restores env reads."""
        monkeypatch.setenv("maintenance_mode", "true")

        assert _settings().maintenance_mode is False
