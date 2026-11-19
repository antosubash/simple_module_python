"""Tests for the production secret-key guard on Settings."""

from __future__ import annotations

import pytest
from simple_module_hosting.settings import Settings


def test_placeholder_secret_ok_in_development() -> None:
    Settings(environment="development", secret_key="change-me-in-production")


def test_placeholder_secret_ok_in_testing() -> None:
    Settings(environment="testing", secret_key="change-me-in-production")


def test_placeholder_secret_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="SM_SECRET_KEY"):
        Settings(environment="production", secret_key="change-me-in-production")


def test_real_secret_accepted_in_production() -> None:
    s = Settings(environment="production", secret_key="real-secret-value")
    assert s.secret_key == "real-secret-value"
    assert s.environment == "production"


@pytest.mark.parametrize("root", ["", " \t\n"])
def test_blank_resolved_root_rejected_in_production(root: str) -> None:
    with pytest.raises(ValueError, match=r"SM_SECRET_KEY.*empty"):
        Settings(_env_file=None, environment="production", secret_key=root)


@pytest.mark.parametrize("environment", ["development", "testing"])
@pytest.mark.parametrize("root", ["", " \t\n"])
def test_blank_direct_settings_root_is_generated(environment: str, root: str) -> None:
    first = Settings(_env_file=None, environment=environment, secret_key=root)
    second = Settings(_env_file=None, environment=environment, secret_key=root)
    assert len(first.secret_key.strip()) >= 40
    assert first.secret_key != second.secret_key


@pytest.mark.parametrize("root", ["", " \t\n"])
def test_app_rejects_blank_root_from_unvalidated_settings_copy(root: str) -> None:
    from simple_module_hosting.app_builder import create_app

    settings = Settings(_env_file=None, environment="production", secret_key="real-root")
    with pytest.raises(ValueError, match=r"SM_SECRET_KEY.*empty"):
        create_app(settings.model_copy(update={"secret_key": root}))
