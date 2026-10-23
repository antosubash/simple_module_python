"""Fallbacks preserve their outcomes while warning once with tracebacks."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from simple_module_core import _i18n_translator, invalidation, menu
from simple_module_db import listeners
from simple_module_hosting import setup_gate


def _assert_warning(caplog, message):
    records = [record for record in caplog.records if message in record.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is not None


def test_plural_failure_warns_once_and_uses_other(monkeypatch, caplog):
    monkeypatch.setattr(_i18n_translator, "_plural_failure_warned", False)
    for _ in range(2):
        assert _i18n_translator._plural_form("not-a-real-locale", 1) == "other"
    _assert_warning(caplog, "Plural locale parsing failed")


def test_audit_identity_failure_warns_once_and_omits_key(monkeypatch, caplog):
    monkeypatch.setattr(listeners, "_entity_pk_failure_warned", False)
    for _ in range(2):
        assert listeners._entity_pk(object()) is None
    _assert_warning(caplog, "Audit identity inspection failed")


def test_invalidation_decoder_warns_once_and_drops_payload(monkeypatch, caplog):
    monkeypatch.setattr(invalidation, "_decode_failure_warned", False)
    for _ in range(2):
        assert invalidation.Invalidation.from_wire("invalid json") is None
    _assert_warning(caplog, "Ignoring undecodable invalidation message")
    assert invalidation.Invalidation.from_wire(invalidation.Invalidation("cache").to_wire())


@pytest.mark.asyncio
async def test_menu_failure_warns_once_per_provider_and_keeps_other_items(caplog):
    registry = menu.MenuRegistry()

    def broken(request):
        yield menu.MenuItem(label="Partial", url="/partial")
        raise RuntimeError("broken provider")

    item = menu.MenuItem(label="Healthy", url="/healthy")
    registry.add_provider(broken)
    registry.add_provider(lambda request: [item])
    for _ in range(2):
        assert await registry.collect_provider_items(SimpleNamespace()) == [item]
    _assert_warning(caplog, "Menu provider")


@pytest.mark.asyncio
async def test_migration_failure_warns_once_and_keeps_gate_closed(monkeypatch, caplog):
    monkeypatch.setattr(setup_gate, "_migration_failure_warned", False)
    check = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(setup_gate.migrations, "migration_status", check)
    snapshot = {"is_current": False}
    app = SimpleNamespace(
        state=SimpleNamespace(
            migration=snapshot, sm=SimpleNamespace(db=SimpleNamespace(engine=None))
        )
    )
    for _ in range(2):
        assert not await setup_gate._database_migrated(app)
    assert app.state.migration is snapshot
    _assert_warning(caplog, "Migration re-check failed")
