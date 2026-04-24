"""Tests for the users-module CLI commands (attached to ``sm`` via
the ``simple_module_cli`` entry-point group).

Strategy: monkeypatch ``users.bootstrap.create_admin`` so tests do not need
a real database. This avoids the complexity of standing up a schema-stamped
SQLite engine inside the same process as the CLI runner and keeps the tests
fast and reliable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner
from users.cli import cli


def _make_result(*, created: bool, email: str = "a@b.test") -> object:
    """Build a fake CreateAdminResult-like object."""
    user = SimpleNamespace(id=uuid.uuid4(), email=email)

    @dataclass
    class _Result:
        user: object
        created: bool

    return _Result(user=user, created=created)


runner = CliRunner()


def _patched_invoke(create_result, args: list[str]):
    async def _fake(session, *, email, password, full_name=None, force=False):
        return create_result

    with (
        patch("users.cli.create_admin", side_effect=_fake),
        patch("users.cli.Settings") as mock_settings_cls,
        patch("users.cli.create_async_engine") as mock_engine,
        patch("users.cli.async_sessionmaker") as mock_factory,
    ):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = session

        engine = AsyncMock()
        engine.dispose = AsyncMock()
        mock_engine.return_value = engine

        mock_settings_cls.return_value = SimpleNamespace(
            database_url="sqlite+aiosqlite:///:memory:"
        )
        return runner.invoke(cli, args)


def test_create_admin_success() -> None:
    """``create-admin`` with valid args creates the admin (exit 0)."""
    result = _patched_invoke(
        _make_result(created=True),
        ["create-admin", "--email", "a@b.test", "--password", "secret12"],
    )
    assert result.exit_code == 0, result.output
    assert "Created admin a@b.test" in result.output


def test_create_admin_already_exists_no_force() -> None:
    """Second invocation without --force exits 1 with 'already exists' message."""
    result = _patched_invoke(
        _make_result(created=False),
        ["create-admin", "--email", "a@b.test", "--password", "secret12"],
    )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_create_admin_force_succeeds() -> None:
    """With --force, second invocation updates the admin (exit 0)."""
    result = _patched_invoke(
        _make_result(created=False),
        ["create-admin", "--email", "a@b.test", "--password", "newpass", "--force"],
    )
    assert result.exit_code == 0, result.output
    assert "Updated admin a@b.test" in result.output


def test_create_admin_missing_email() -> None:
    """Invoking create-admin without --email fails with usage error (exit != 0)."""
    result = runner.invoke(cli, ["create-admin", "--password", "secret"])
    assert result.exit_code != 0


def test_group_help() -> None:
    """``sm users --help`` shows the subgroup's commands."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "create-admin" in result.output


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_aliases(flag: str) -> None:
    result = runner.invoke(cli, [flag])
    assert result.exit_code == 0
