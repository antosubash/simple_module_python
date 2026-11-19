"""The anonymous migrations action must not echo the failure to the client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic import command
from fastapi import HTTPException
from simple_module_hosting._secret_key import SecretKeyUnavailableError
from simple_module_hosting.setup_wizard import migrate
from simple_module_hosting.setup_wizard.migrate import apply_migrations
from sqlalchemy.engine import make_url


def _request(correlation_id):
    engine = SimpleNamespace(url=make_url("sqlite+aiosqlite:///:memory:"))
    return SimpleNamespace(
        state=SimpleNamespace(correlation_id=correlation_id),
        app=SimpleNamespace(
            state=SimpleNamespace(sm=SimpleNamespace(db=SimpleNamespace(engine=engine)))
        ),
    )


_SECRET = "postgresql://admin:hunter2@db.internal/prod"


@pytest.fixture(autouse=True)
def _verified_first_run(monkeypatch):
    async def status(*args):
        return {
            "head_revision": "head",
            "current_revision": None,
            "is_current": False,
            "pending_count": 1,
        }

    async def eligible(*args):
        return True

    monkeypatch.setattr("simple_module_hosting.migrations.migration_status", status)
    monkeypatch.setattr(migrate, "is_first_run", eligible)


async def test_migration_failure_detail_is_redacted(monkeypatch, caplog) -> None:
    def _boom(*_args, **_kwargs) -> None:
        raise RuntimeError(f"could not connect to {_SECRET}")

    monkeypatch.setattr(command, "upgrade", _boom)
    request = _request("cid-123")

    with pytest.raises(HTTPException) as info:
        await apply_migrations(request, {})

    assert info.value.status_code == 500
    assert _SECRET not in str(info.value.detail)
    assert "cid-123" in str(info.value.detail)
    # The operator still gets the real error, in the log.
    assert _SECRET in caplog.text


async def test_root_persistence_failure_detail_is_redacted(monkeypatch, caplog):
    monkeypatch.setattr(command, "upgrade", lambda *_args: None)
    monkeypatch.setattr(
        "simple_module_hosting.migrations.migration_status",
        AsyncMock(side_effect=[{"is_current": False}, {"is_current": True}]),
    )
    monkeypatch.setattr(
        migrate, "run_deferred_startup", AsyncMock(side_effect=SecretKeyUnavailableError(_SECRET))
    )
    with pytest.raises(HTTPException) as info:
        await apply_migrations(_request(""), {})
    assert info.value.status_code == 503
    assert _SECRET not in str(info.value.detail)
    assert _SECRET in caplog.text


async def test_in_process_migration_keeps_app_logging(monkeypatch) -> None:
    """alembic's fileConfig must not leave the app's root logging replaced."""
    import logging

    root = logging.getLogger()
    sentinel = logging.NullHandler()
    root.addHandler(sentinel)
    level = root.level

    def _clobber(*_args, **_kwargs) -> None:
        # What env.py's fileConfig does to the root logger.
        root.handlers[:] = [logging.StreamHandler()]
        root.setLevel(logging.ERROR)
        raise RuntimeError("stop after clobbering")

    monkeypatch.setattr(command, "upgrade", _clobber)
    request = _request("")
    try:
        with pytest.raises(HTTPException):
            await apply_migrations(request, {})
        assert sentinel in root.handlers
        assert root.level == level
    finally:
        root.removeHandler(sentinel)
