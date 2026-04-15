"""Tests for the sm-users CLI (users.cli).

Strategy: monkeypatch ``users.bootstrap.create_admin`` so tests do not need
a real database.  This avoids the complexity of standing up a schema-stamped
SQLite engine inside the same process as the CLI runner and keeps the tests
fast and reliable.

The monkeypatching approach was chosen over a full CLI integration test
because the CLI creates its own engine + session (by design — it is safe to
run while the web app is down), which makes in-process schema setup fragile
when using ``aiosqlite`` with ``typer.testing.CliRunner``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner
from users.cli import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(*, created: bool, email: str = "a@b.test") -> object:
    """Build a fake CreateAdminResult-like object."""
    user = SimpleNamespace(id=uuid.uuid4(), email=email)

    @dataclass
    class _Result:
        user: object
        created: bool

    return _Result(user=user, created=created)


runner = CliRunner()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_admin_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """``create-admin`` with valid args creates the admin (exit 0)."""
    mock_result = _make_result(created=True)

    async def _fake_create_admin(session, *, email, password, full_name=None, force=False):
        return mock_result

    with (
        patch("users.cli.create_admin", side_effect=_fake_create_admin),
        patch("users.cli.Settings") as mock_settings_cls,
        patch("users.cli.create_async_engine") as mock_engine,
        patch("users.cli.async_sessionmaker") as mock_factory,
    ):
        # Wire up the mocks so the async context manager works
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_session

        mock_engine_instance = AsyncMock()
        mock_engine_instance.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_instance

        mock_settings_cls.return_value = SimpleNamespace(
            database_url="sqlite+aiosqlite:///:memory:"
        )

        result = runner.invoke(
            app,
            ["create-admin", "--email", "a@b.test", "--password", "secret12"],
        )

    assert result.exit_code == 0
    assert "Created admin a@b.test" in result.output


def test_create_admin_already_exists_no_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second invocation without --force exits 1 with 'already exists' message."""
    mock_result = _make_result(created=False)

    async def _fake_create_admin(session, *, email, password, full_name=None, force=False):
        return mock_result

    with (
        patch("users.cli.create_admin", side_effect=_fake_create_admin),
        patch("users.cli.Settings") as mock_settings_cls,
        patch("users.cli.create_async_engine") as mock_engine,
        patch("users.cli.async_sessionmaker") as mock_factory,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_session

        mock_engine_instance = AsyncMock()
        mock_engine_instance.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_instance

        mock_settings_cls.return_value = SimpleNamespace(
            database_url="sqlite+aiosqlite:///:memory:"
        )

        result = runner.invoke(
            app,
            ["create-admin", "--email", "a@b.test", "--password", "secret12"],
        )

    assert result.exit_code == 1
    assert "already exists" in result.output


def test_create_admin_force_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """With --force, second invocation updates the admin (exit 0)."""
    mock_result = _make_result(created=False)

    async def _fake_create_admin(session, *, email, password, full_name=None, force=False):
        assert force is True
        return mock_result

    with (
        patch("users.cli.create_admin", side_effect=_fake_create_admin),
        patch("users.cli.Settings") as mock_settings_cls,
        patch("users.cli.create_async_engine") as mock_engine,
        patch("users.cli.async_sessionmaker") as mock_factory,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_session

        mock_engine_instance = AsyncMock()
        mock_engine_instance.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_instance

        mock_settings_cls.return_value = SimpleNamespace(
            database_url="sqlite+aiosqlite:///:memory:"
        )

        result = runner.invoke(
            app,
            ["create-admin", "--email", "a@b.test", "--password", "newpass", "--force"],
        )

    assert result.exit_code == 0
    assert "Updated admin a@b.test" in result.output


def test_create_admin_missing_email() -> None:
    """Invoking create-admin without --email fails with usage error (exit != 0)."""
    result = runner.invoke(app, ["create-admin", "--password", "secret"])
    assert result.exit_code != 0


def test_app_help() -> None:
    """``sm-users --help`` shows the top-level help text and lists create-admin."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "create-admin" in result.output
