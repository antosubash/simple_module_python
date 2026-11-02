"""Statement DML lands in ``audit_log_audit_entry`` through the app's sink (#557)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from audit_log.models import AuditEntry
from background_tasks.models import TaskExecution
from simple_module_db import UnauditedWriteError, all_tenants, tenant_context
from sqlalchemy import select, update


async def _entries(app) -> list[AuditEntry]:
    async with app.state.sm.db.session_factory() as session:
        with all_tenants():
            stmt = select(AuditEntry).where(AuditEntry.entity_type == TaskExecution.__name__)
            return list((await session.execute(stmt)).scalars())


@pytest.fixture
async def task_id(app) -> str:
    async with app.state.sm.db.session_factory() as session:
        row = TaskExecution(task_name="demo.task")
        session.add(row)
        await session.commit()
        return str(row.id)


async def _execute(app, stmt, *, commit: bool = True) -> None:
    async with app.state.sm.db.session_factory() as session:
        with tenant_context("tenant-a"):
            await session.execute(stmt)
            if commit:
                await session.commit()


async def test_bulk_update_is_audited_with_the_tenant(app, task_id):
    await _execute(app, update(TaskExecution).values(worker="w1"))
    bulk = [e for e in await _entries(app) if e.action == "bulk_updated"]
    assert [(e.entity_id, e.tenant_id) for e in bulk] == [(task_id, "tenant-a")]
    assert bulk[0].changes == [{"field": "worker", "new": "w1"}]


async def test_heartbeat_update_writes_no_entry(app, task_id):
    await _execute(app, update(TaskExecution).values(heartbeat_at=datetime.now(UTC)))
    assert [e.action for e in await _entries(app)] == ["created"]


async def test_rolled_back_write_leaves_no_entry(app, task_id):
    await _execute(app, update(TaskExecution).values(worker="w2"), commit=False)
    assert [e.action for e in await _entries(app)] == ["created"]


async def test_refuse_unaudited_dml_setting(app, task_id):
    quiet = update(TaskExecution).values(worker="w3").execution_options(sm_audit=False)
    await _execute(app, quiet)
    app.state.audit_log.settings.refuse_unaudited_dml = True
    with pytest.raises(UnauditedWriteError):
        await _execute(app, quiet)
    assert [e.action for e in await _entries(app)] == ["created"]
