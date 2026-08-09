"""Tests for select_auth_provider — picking one of several installed providers."""

from __future__ import annotations

import logging
import os

import pytest
from simple_module_core.discovery import (
    DEFAULT_AUTH_PROVIDER,
    resolve_auth_provider,
    select_auth_provider,
)
from simple_module_core.module import ModuleBase, ModuleMeta


class FakeUsers(ModuleBase):
    meta = ModuleMeta(name="Users")
    _is_auth_provider = True


class FakeKeycloak(ModuleBase):
    meta = ModuleMeta(name="Keycloak")
    _is_auth_provider = True


class FakeDashboard(ModuleBase):
    meta = ModuleMeta(name="Dashboard")


def _names(modules):
    return [m.meta.name for m in modules]


class TestSelectAuthProvider:
    def test_default_keeps_users_and_drops_keycloak(self):
        """Both installed (the dev workspace) → the default provider wins, no SM020."""
        result = select_auth_provider([FakeUsers(), FakeKeycloak(), FakeDashboard()])
        assert _names(result) == ["Users", "Dashboard"]

    def test_preferred_keycloak_drops_users(self):
        result = select_auth_provider([FakeUsers(), FakeKeycloak()], "keycloak")
        assert _names(result) == ["Keycloak"]

    def test_match_is_case_insensitive(self):
        result = select_auth_provider([FakeUsers(), FakeKeycloak()], "KeyCloak")
        assert _names(result) == ["Keycloak"]

    def test_non_provider_modules_keep_their_order(self):
        modules = [FakeDashboard(), FakeKeycloak(), FakeUsers()]
        assert _names(select_auth_provider(modules)) == ["Dashboard", "Users"]

    def test_lone_provider_survives_a_mismatched_preference(self):
        """A keycloak-only host keeps keycloak even at the default preference."""
        result = select_auth_provider([FakeKeycloak(), FakeDashboard()], "users")
        assert _names(result) == ["Keycloak", "Dashboard"]

    def test_no_providers_is_untouched(self):
        """SM021 territory — nothing to select, and nothing to drop."""
        assert _names(select_auth_provider([FakeDashboard()])) == ["Dashboard"]

    def test_unknown_preference_leaves_the_conflict_for_sm020(self):
        """Naming a provider that isn't installed must not silently pick one."""
        result = select_auth_provider([FakeUsers(), FakeKeycloak()], "oidc")
        assert _names(result) == ["Users", "Keycloak"]

    def test_selection_is_logged(self, caplog):
        with caplog.at_level(logging.INFO, logger="simple_module_core.discovery"):
            select_auth_provider([FakeUsers(), FakeKeycloak()])
        assert any("Keycloak" in rec.getMessage() for rec in caplog.records)

    def test_input_is_not_mutated(self):
        modules = [FakeUsers(), FakeKeycloak()]
        select_auth_provider(modules)
        assert len(modules) == 2


class TestResolveAuthProvider:
    @pytest.fixture(autouse=True)
    def _isolated_environ(self, monkeypatch, tmp_path):
        """Swap in a throwaway ``os.environ``.

        ``resolve_auth_provider`` merges ``.env`` into the real environment via
        ``setdefault``, which ``monkeypatch.delenv(raising=False)`` can't undo —
        it records nothing for a key that was already absent. Without this the
        provider chosen here would leak into every later test in the session.
        """
        monkeypatch.setattr(os, "environ", dict(os.environ))
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        monkeypatch.delenv("SM_AUTH_PROVIDER", raising=False)

    def test_defaults_to_users(self):
        assert resolve_auth_provider() == DEFAULT_AUTH_PROVIDER

    def test_reads_the_env_var(self, monkeypatch):
        monkeypatch.setenv("SM_AUTH_PROVIDER", "keycloak")
        assert resolve_auth_provider() == "keycloak"

    def test_blank_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("SM_AUTH_PROVIDER", "  ")
        assert resolve_auth_provider() == DEFAULT_AUTH_PROVIDER

    def test_reads_dotenv_when_env_is_unset(self, tmp_path):
        (tmp_path / ".env").write_text("SM_AUTH_PROVIDER=keycloak\n", encoding="utf-8")
        assert resolve_auth_provider() == "keycloak"

    def test_real_environment_wins_over_dotenv(self, monkeypatch, tmp_path):
        (tmp_path / ".env").write_text("SM_AUTH_PROVIDER=keycloak\n", encoding="utf-8")
        monkeypatch.setenv("SM_AUTH_PROVIDER", "users")
        assert resolve_auth_provider() == "users"
