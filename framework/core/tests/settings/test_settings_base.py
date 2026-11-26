"""DB-backed settings isolation and shared link-base validation.

``DbBackedSettings`` must not read the environment at all — GH #283.

The bug this guards was reported against ``background_tasks``, but the cause
was shared by every bundled settings class: subclassing ``BaseSettings``
without an ``env_prefix`` doesn't disable env reads, it un-namespaces them.
Fields then resolve from bare names — ``password``, ``backend``, ``base_url``
— which are common enough in a container that an unrelated component setting
one silently reconfigures the app.
"""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings
from simple_module_core.settings.settings_base import DbBackedSettings
from simple_module_core.settings.url_validation import validate_http_base_url


class _Example(DbBackedSettings):
    password: str = ""
    backend: str = "filesystem"
    base_url: str = "http://localhost:8000"
    enabled: bool = False
    retries: int = 3


class _LeakyExample(BaseSettings):
    """The old shape, kept as the contrast the test is asserting against."""

    password: str = ""


def test_bare_field_names_are_not_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("password", "hunter2")
    monkeypatch.setenv("backend", "s3")
    monkeypatch.setenv("base_url", "http://evil.example.com")
    monkeypatch.setenv("enabled", "true")
    monkeypatch.setenv("retries", "99")

    settings = _Example()

    assert settings.password == ""
    assert settings.backend == "filesystem"
    assert settings.base_url == "http://localhost:8000"
    assert settings.enabled is False
    assert settings.retries == 3


def test_plain_base_settings_would_have_read_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the behaviour being defended against, so the test can't quietly pass."""
    monkeypatch.setenv("password", "hunter2")

    assert _LeakyExample().password == "hunter2"


def test_uppercase_names_are_ignored_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """pydantic-settings matches env case-insensitively by default."""
    monkeypatch.setenv("PASSWORD", "hunter2")

    assert _Example().password == ""


def test_constructor_values_still_win() -> None:
    """Hydration from the DB goes through the constructor, so it must work."""
    settings = _Example(password="from-db", retries=7)

    assert settings.password == "from-db"
    assert settings.retries == 7


def test_dotenv_file_is_not_read(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The host loads `.env` into `os.environ`; these classes still ignore it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("password=from-dotenv\n", encoding="utf-8")

    assert _Example().password == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" \t\n ", ""),
        ("  https://EXAMPLE.com/app/  ", "https://EXAMPLE.com/app/"),
        ("https://example.com/" + "a" * 2063, "https://example.com/" + "a" * 2063),
    ],
)
def test_core_http_base_url_preserves_trimmed_input(value: str, expected: str) -> None:
    assert validate_http_base_url(value, "link_base") == expected


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "https:///example.com",
        "https://:password@example.com",
        "https://@example.com",
        "https://example.com/path\x7f",
        "https://example.com/path\tsegment",
        "https://example.com\\path",
        "https://example.com/app?",
        "https://example.com/app#section",
        "https://example.com/" + "a" * 2064,
    ],
)
def test_core_http_base_url_errors_identify_callers_field(value: str) -> None:
    with pytest.raises(ValueError, match="link_base must be an absolute http\\(s\\) URL"):
        validate_http_base_url(value, "link_base")
