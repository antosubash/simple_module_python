"""Tests for ``resolve_bootstrap_credentials`` — the three-tier resolver shared
between the boot-time admin seeder and the login-page dev-quick-fill UI.

Regression coverage for issue #159: previously the login page only consulted
``UsersSettings`` + ``os.environ``, so an admin seeded via the ``.env``
fallback was created but the dev-quick-login button never showed.
"""

from __future__ import annotations

import pytest
from users import bootstrap as bootstrap_module
from users.bootstrap import BOOTSTRAP_ENV_KEYS, resolve_bootstrap_credentials
from users.settings import UsersSettings


def _bare_users_settings(**overrides: str) -> UsersSettings:
    """UsersSettings with all required-field defaults filled in."""
    defaults = {
        "reset_password_token_secret": "test-secret",
        "verification_token_secret": "test-secret",
    }
    defaults.update(overrides)
    return UsersSettings(**defaults)


def test_prefers_settings_over_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-empty UsersSettings field beats the same key on ``os.environ``."""
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_EMAIL", "env@example.com")
    settings = _bare_users_settings(bootstrap_email="settings@example.com")

    resolved = resolve_bootstrap_credentials(settings)

    assert resolved["bootstrap_email"] == "settings@example.com"


def test_falls_back_to_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty UsersSettings field falls through to ``os.environ``."""
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_EMAIL", "env@example.com")
    settings = _bare_users_settings()

    resolved = resolve_bootstrap_credentials(settings)

    assert resolved["bootstrap_email"] == "env@example.com"


def test_falls_back_to_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """When settings + ``os.environ`` are empty, ``.env`` is consulted last."""
    monkeypatch.setattr(
        bootstrap_module,
        "_read_dotenv_bootstrap_vars",
        lambda: {
            "SM_USERS_BOOTSTRAP_EMAIL": "dotenv@example.com",
            "SM_USERS_BOOTSTRAP_PASSWORD": "DotenvPass1!",
        },
    )
    settings = _bare_users_settings()

    resolved = resolve_bootstrap_credentials(settings)

    assert resolved["bootstrap_email"] == "dotenv@example.com"
    assert resolved["bootstrap_password"] == "DotenvPass1!"


def test_returns_empty_strings_when_nothing_set() -> None:
    """All four keys are present in the result even when unresolved."""
    settings = _bare_users_settings()

    resolved = resolve_bootstrap_credentials(settings)

    assert set(resolved) == set(BOOTSTRAP_ENV_KEYS)
    assert all(v == "" for v in resolved.values())
