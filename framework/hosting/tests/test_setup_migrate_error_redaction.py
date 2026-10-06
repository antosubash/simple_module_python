"""The anonymous migrations action must not echo the failure to the client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from alembic import command
from fastapi import HTTPException
from simple_module_hosting.setup_wizard.migrate import apply_migrations

_SECRET = "postgresql://admin:hunter2@db.internal/prod"


async def test_migration_failure_detail_is_redacted(monkeypatch, caplog) -> None:
    def _boom(*_args, **_kwargs) -> None:
        raise RuntimeError(f"could not connect to {_SECRET}")

    monkeypatch.setattr(command, "upgrade", _boom)
    request = SimpleNamespace(state=SimpleNamespace(correlation_id="cid-123"))

    with pytest.raises(HTTPException) as info:
        await apply_migrations(request, {})

    assert info.value.status_code == 500
    assert _SECRET not in str(info.value.detail)
    assert "cid-123" in str(info.value.detail)
    # The operator still gets the real error, in the log.
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
    request = SimpleNamespace(state=SimpleNamespace(correlation_id=""))
    try:
        with pytest.raises(HTTPException):
            await apply_migrations(request, {})
        assert sentinel in root.handlers
        assert root.level == level
    finally:
        root.removeHandler(sentinel)
