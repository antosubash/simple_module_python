"""A development boot reports SM011 once the database is open (#895)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.services import DiagnosticsState
from simple_module_hosting import _table_coverage
from simple_module_hosting._table_coverage import add_table_coverage
from sqlalchemy.ext.asyncio import create_async_engine

_BOOT = Diagnostic(
    level=DiagnosticLevel.WARNING, code="SM019", message="boot finding", module_name="Demo"
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE TABLE orders_order (id INTEGER)"))
    yield engine
    await engine.dispose()


def _app(engine, state: DiagnosticsState) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(diagnostics=state, db=SimpleNamespace(engine=engine))
        )
    )


@pytest.fixture(autouse=True)
def _module_tables(monkeypatch):
    monkeypatch.setattr(
        _table_coverage, "module_table_names", lambda modules: {"orders_order", "orders_line"}
    )


async def test_hosting_table_coverage_survives_rerun(engine, capsys):
    state = DiagnosticsState(runner=lambda: [_BOOT])
    state.rerun()

    await add_table_coverage(_app(engine, state), [])

    assert [d.code for d in state.results] == ["SM019", "SM011"]
    assert "orders_line" in state.results[1].message
    assert "SM011" in capsys.readouterr().err
    assert [d.code for d in state.rerun()] == ["SM019", "SM011"]


async def test_hosting_table_coverage_is_quiet_when_covered(engine, monkeypatch):
    monkeypatch.setattr(_table_coverage, "module_table_names", lambda modules: {"orders_order"})
    state = DiagnosticsState(runner=lambda: [_BOOT])
    state.rerun()

    await add_table_coverage(_app(engine, state), [])

    assert [d.code for d in state.rerun()] == ["SM019"]


async def test_hosting_table_coverage_skips_without_a_runner(engine):
    # Outside development no diagnostics run, so the database is not inspected.
    state = DiagnosticsState()

    await add_table_coverage(_app(engine, state), [])

    assert state.results == []
    assert state.supported is False
