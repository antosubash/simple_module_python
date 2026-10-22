"""Statement DML is audited like a flush (#557): ORM bulk, Core DML, ``text()`` via helper."""

from __future__ import annotations

import pytest
from _audit_models import (
    AuditTestItem,
    ExcludedModel,
    PartialExcludeModel,
    SoftDeleteItem,
)
from _models import _TenantItem
from simple_module_db import bulk_audit, record_bulk_audit, tenant_context
from simple_module_db.audit import AuditRecord
from sqlalchemy import bindparam, delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


async def _ids(session: AsyncSession, where=None) -> list[str]:
    query = select(AuditTestItem.id).order_by(AuditTestItem.id)
    if where is not None:
        query = query.where(where)
    return [str(i) for i in (await session.execute(query)).scalars()]


async def test_orm_bulk_update_records_each_row_with_set_values(audited):
    _state, session, recorder = audited
    expected = await _ids(session, AuditTestItem.value >= 1)
    await session.execute(update(AuditTestItem).where(AuditTestItem.value >= 1).values(name="x"))
    assert sorted(r.entity_id for r in recorder.records) == expected
    assert {r.action for r in recorder.records} == {"bulk_updated"}
    assert recorder.records[0].changes == [{"field": "name", "new": "x"}]


async def test_orm_bulk_delete_records_each_row(audited):
    _state, session, recorder = audited
    expected = await _ids(session)
    await session.execute(delete(AuditTestItem))
    assert sorted(r.entity_id for r in recorder.records) == expected
    assert {(r.action, tuple(r.changes)) for r in recorder.records} == {("bulk_deleted", ())}


async def test_core_dml_on_table_is_audited(audited):
    _state, session, recorder = audited
    table = AuditTestItem.__table__
    target = (await _ids(session, AuditTestItem.value == 2))[0]
    await session.execute(update(table).where(table.c.value == 2).values(value=table.c.value + 1))
    await session.execute(delete(table).where(table.c.value == 0))
    actions = [(r.action, r.entity_id) for r in recorder.records]
    assert actions[0] == ("bulk_updated", target)
    assert recorder.records[0].changes[0]["field"] == "value"
    assert actions[1][0] == "bulk_deleted"


async def test_insert_statement_records_one_summary_row(audited):
    _state, session, recorder = audited
    rows = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
    await session.execute(insert(AuditTestItem), rows)
    await session.execute(insert(AuditTestItem.__table__).values(name="c", value=3))
    assert [(r.action, r.entity_id) for r in recorder.records] == [("bulk_inserted", "*")] * 2
    assert {"field": "rowcount", "new": 2} in recorder.records[0].changes
    assert {"field": "name", "new": "c"} in recorder.records[1].changes


async def test_over_the_cap_records_one_summary_without_literals(audited, monkeypatch):
    _state, session, recorder = audited
    monkeypatch.setattr(bulk_audit, "BULK_AUDIT_ID_CAP", 2)
    await session.execute(update(AuditTestItem).where(AuditTestItem.value < 99).values(name="s"))
    assert [(r.action, r.entity_id) for r in recorder.records] == [("bulk_updated", "*")]
    changes = {c["field"]: c["new"] for c in recorder.records[0].changes}
    assert changes["rowcount"] == 3 and changes["truncated"] is True and changes["name"] == "s"
    assert "99" not in changes["where_sql"] and "value" in changes["where_sql"]


async def test_excluded_columns_and_models(audited):
    _state, session, recorder = audited
    session.add_all([PartialExcludeModel(username="u"), ExcludedModel(name="e")])
    await session.flush()
    recorder.records.clear()
    await session.execute(update(PartialExcludeModel).values(password_hash="h"))
    await session.execute(update(ExcludedModel).values(name="z"))
    await session.execute(update(AuditTestItem).values(updated_by="bot"))
    assert recorder.records == []
    await session.execute(update(PartialExcludeModel).values(username="v", password_hash="h2"))
    assert recorder.records[0].changes == [{"field": "username", "new": "v"}]


async def test_bulk_soft_delete_is_recorded(audited):
    _state, session, recorder = audited
    session.add(SoftDeleteItem(title="t"))
    await session.flush()
    recorder.records.clear()
    await session.execute(update(SoftDeleteItem).values(is_deleted=True))
    assert [r.action for r in recorder.records] == ["bulk_soft_deleted"]


async def test_bulk_update_by_primary_key_uses_the_rows(audited):
    _state, session, recorder = audited
    ids = [int(i) for i in await _ids(session)]
    await session.execute(update(AuditTestItem), [{"id": i, "name": "pk"} for i in ids[:2]])
    assert [r.entity_id for r in recorder.records] == [str(i) for i in ids[:2]]
    assert recorder.records[0].changes == [{"field": "name"}]


async def test_prefetch_keeps_the_tenant_scope(audited):
    _state, session, recorder = audited
    for tenant in ("a", "b"):
        with tenant_context(tenant):
            session.add(_TenantItem(name=tenant))
            await session.flush()
    recorder.records.clear()
    with tenant_context("a"):
        await session.execute(update(_TenantItem).values(name="renamed"))
        own = (await session.execute(select(_TenantItem.id))).scalars().all()
    assert [r.entity_id for r in recorder.records] == [str(i) for i in own]


async def test_opt_out_and_strict_mode(audited):
    state, session, recorder = audited
    opted_out = update(AuditTestItem).values(name="quiet").execution_options(sm_audit=False)
    await session.execute(opted_out)
    assert recorder.records == []
    state.refuse_unaudited_dml = lambda: True
    with pytest.raises(bulk_audit.UnauditedWriteError):
        await session.execute(opted_out)
    # Excluded-only writes and excluded models would not be audited anyway.
    await session.execute(update(ExcludedModel).values(name="z").execution_options(sm_audit=False))


async def test_sink_failure_never_breaks_the_write(audited):
    state, session, _recorder = audited

    def _boom(session: Session, records: list[AuditRecord]) -> None:
        raise RuntimeError("sink down")

    state.audit_callback = _boom
    await session.execute(update(AuditTestItem).values(name="kept"))
    names = (await session.execute(select(func.count()).where(AuditTestItem.name == "kept"))).one()
    assert names[0] == 3


async def test_record_bulk_audit_for_text_writes(audited):
    _state, session, recorder = audited
    await session.execute(text("UPDATE test_audit_item SET value = 7"))
    assert recorder.records == []
    record_bulk_audit(session, AuditTestItem, "bulk_updated", [1, 2], {"value": 7})
    record_bulk_audit(session, "Raw", "bulk_deleted", None)
    assert recorder.summary() == [
        ("AuditTestItem", "bulk_updated", "1"),
        ("AuditTestItem", "bulk_updated", "2"),
        ("Raw", "bulk_deleted", "*"),
    ]
    assert recorder.records[0].changes == [{"field": "value", "new": 7}]


async def test_unaudited_engine_records_nothing(audited):
    state, session, recorder = audited
    state.audit_callback = None
    await session.execute(update(AuditTestItem).values(name="n"))
    record_bulk_audit(session, AuditTestItem, "bulk_updated", [1])
    assert recorder.records == []


async def test_parameterized_update_and_delete_are_audited(audited):
    _state, session, recorder = audited
    target = (await _ids(session, AuditTestItem.name == "n1"))[0]
    stmt = update(AuditTestItem).where(AuditTestItem.name == bindparam("target")).values(value=50)
    await session.execute(stmt, {"target": "n1"})
    assert [(r.action, r.entity_id) for r in recorder.records] == [("bulk_updated", target)]
    recorder.records.clear()
    gone = delete(AuditTestItem).where(AuditTestItem.name == bindparam("target"))
    await session.execute(gone, {"target": "n2"})
    assert [r.action for r in recorder.records] == ["bulk_deleted"]
    assert len(recorder.records) == 1 and recorder.records[0].entity_id != "*"


async def test_broken_prefetch_never_breaks_the_write(audited, monkeypatch):
    _state, session, recorder = audited

    def _boom(*_args, **_kwargs):
        raise RuntimeError("prefetch broke")

    monkeypatch.setattr(bulk_audit, "_prefetch_ids", _boom)
    await session.execute(update(AuditTestItem).where(AuditTestItem.value >= 0).values(name="ok"))
    count = (await session.execute(select(func.count()).where(AuditTestItem.name == "ok"))).one()
    assert count[0] == 3
    assert [r.entity_id for r in recorder.records] == ["*"]
    monkeypatch.setattr(bulk_audit, "_plan", _boom)
    await session.execute(update(AuditTestItem).values(name="ok2"))
    await session.execute(update(AuditTestItem).values(name="ok3").execution_options(sm_audit=False))
