"""A settings class with no ``env_prefix`` is not pinned by bare env vars (#486 review).

A plain ``BaseSettings`` reads bare, case-insensitive names, so ``USER`` or
``HOME`` in the process environment would otherwise mark fields called
``user``/``home`` as env-supplied, refuse every admin edit and drop the
stored value.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from settings.hydrate import build_settings, env_supplied_fields


class _Unprefixed(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    user: str = "default-user"
    home: str = "/default"


class _Prefixed(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_prefix="SM_TEST_UNPREFIXED_")

    user: str = "default-user"


class _Seeded(_Unprefixed):
    @classmethod
    def env_seeded_fields(cls) -> frozenset[str]:
        return frozenset({"home"})


def test_bare_env_vars_pin_nothing_on_an_unprefixed_class(monkeypatch):
    monkeypatch.setenv("USER", "from-env")
    monkeypatch.setenv("HOME", "/from/env")
    assert env_supplied_fields(_Unprefixed) == frozenset()
    built = build_settings(_Unprefixed, {"user": ("from-db", "string")})
    assert built.user == "from-db"


def test_a_prefixed_class_is_still_pinned_by_its_own_vars(monkeypatch):
    monkeypatch.setenv("SM_TEST_UNPREFIXED_USER", "from-env")
    assert env_supplied_fields(_Prefixed) == frozenset({"user"})


def test_explicitly_env_seeded_fields_still_count(monkeypatch):
    monkeypatch.setenv("HOME", "/from/env")
    assert env_supplied_fields(_Seeded) == frozenset({"home"})
