"""A credential embedded in a URL is a secret, whatever the field is called.

The name-based rule (``password|secret|api_key|…``) never fires for
``broker_url``, ``result_backend``, ``redis_url`` or ``database_url`` — yet a
DSN is exactly where a production deployment keeps its Redis and Postgres
passwords. Those fields are ``env_readable``, so the admin settings screen and
the ``known_keys`` suggestion list were both handing the credential back in
clear text to anyone who could open them.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from settings._module_settings import SECRET_MASK, _field_view

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_CREATE = "/admin/settings/create"


class _Dsns(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_DEMO_", extra="ignore")

    database_url: str = "postgresql://u:p@h/db"
    plain_url: str = "https://example.com/health"
    empty_url: str = ""
    port: int = 5432


def _view(name: str) -> object:
    return _field_view(name, _Dsns(), "SM_DEMO_")


class TestUrlEmbeddedCredentials:
    def test_a_password_in_the_authority_is_masked(self):
        field = _view("database_url")

        assert field.is_secret is True
        assert field.value == SECRET_MASK
        assert field.default == SECRET_MASK

    def test_a_url_without_a_password_stays_visible(self):
        field = _view("plain_url")

        assert field.is_secret is False
        assert field.value == "https://example.com/health"

    def test_an_empty_value_is_not_a_url(self):
        field = _view("empty_url")

        assert field.is_secret is False
        assert field.value == ""

    def test_a_non_string_is_not_parsed_as_a_url(self):
        field = _view("port")

        assert field.is_secret is False
        assert field.value == 5432

    def test_a_malformed_url_does_not_raise(self):
        """``urlsplit`` raises ValueError on e.g. a bad IPv6 literal."""

        class _Broken(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="SM_DEMO_", extra="ignore")

            dsn: str = "http://[::1:80/path"

        field = _field_view("dsn", _Broken(), "SM_DEMO_")

        assert field.is_secret is False

    def test_the_env_value_is_masked_too(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SM_DEMO_PLAIN_URL", "redis://someone:hunter2@cache:6379/0")

        field = _field_view("plain_url", _Dsns(), "SM_DEMO_")

        assert field.is_secret is True
        assert field.env_value == SECRET_MASK
        assert "hunter2" not in str(field.value)


class TestKnownKeysNeverLeaksADsn:
    async def test_a_broker_url_with_a_password_is_masked(
        self, authenticated_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``background_tasks.broker_url`` is env-readable and carries a password."""
        monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://:hunter2@cache:6379/0")

        resp = await authenticated_client.get(_CREATE, headers=_INERTIA)
        assert resp.status_code == 200, resp.text[:400]
        entries = resp.json()["props"]["known_keys"]
        broker = next(e for e in entries if e["key"] == "background_tasks.broker_url")

        assert broker["is_secret"] is True
        assert broker["env_value"] == SECRET_MASK
        assert "hunter2" not in resp.text

    async def test_a_password_free_broker_url_stays_visible(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(_CREATE, headers=_INERTIA)
        entries = resp.json()["props"]["known_keys"]
        broker = next(e for e in entries if e["key"] == "background_tasks.broker_url")

        assert broker["is_secret"] is False
        assert broker["default"].startswith("redis://")


class TestMaskSentinelIsNeverStored:
    def test_a_masked_dsn_echoed_back_is_dropped(self):
        """The editor renders the mask; submitting it must not overwrite the
        real DSN with a row of dots. The name rule does not know
        ``broker_url`` is a secret, so the sentinel has to be the signal."""
        from settings.endpoints.module_api import _strip_mask_sentinels

        assert _strip_mask_sentinels({"broker_url": SECRET_MASK, "queue": "celery"}) == {
            "queue": "celery"
        }
