"""Environment-only bootstrap credentials, shared by seeding and dev quick-fill."""

from users.core import bootstrap as bootstrap_module
from users.core.bootstrap import BOOTSTRAP_ENV_KEYS, resolve_bootstrap_credentials


def test_environ_wins_over_dotenv(monkeypatch):
    monkeypatch.setenv("SM_USERS_BOOTSTRAP_EMAIL", "env@example.com")
    monkeypatch.setattr(
        bootstrap_module,
        "_read_dotenv_bootstrap_vars",
        lambda: {"SM_USERS_BOOTSTRAP_EMAIL": "dotenv@example.com"},
    )
    assert resolve_bootstrap_credentials()["bootstrap_email"] == "env@example.com"


def test_falls_back_to_dotenv(monkeypatch):
    monkeypatch.setattr(
        bootstrap_module,
        "_read_dotenv_bootstrap_vars",
        lambda: {
            "SM_USERS_BOOTSTRAP_EMAIL": "dotenv@example.com",
            "SM_USERS_BOOTSTRAP_PASSWORD": "DotenvPass1!",
        },
    )
    resolved = resolve_bootstrap_credentials()
    assert resolved["bootstrap_email"] == "dotenv@example.com"
    assert resolved["bootstrap_password"] == "DotenvPass1!"


def test_returns_all_empty_credentials_when_unconfigured():
    resolved = resolve_bootstrap_credentials()
    assert set(resolved) == set(BOOTSTRAP_ENV_KEYS)
    assert all(v == "" for v in resolved.values())
