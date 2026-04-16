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
