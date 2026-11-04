"""Audit targets and ORM lifecycle regressions (#810, #811)."""

import pytest
from _audit_models import AuditTestItem, SoftDeleteItem
from simple_module_core.correlation import correlation_id
from simple_module_db.listeners import current_user_id
from sqlalchemy import bindparam, delete, select, update
from sqlalchemy.orm import with_loader_criteria


@pytest.mark.parametrize("operation", [update, delete], ids=["update", "delete"])
@pytest.mark.parametrize("value", [2, 99], ids=["one-match", "no-match"])
async def test_bulk_audit_prefetch_preserves_loader_criteria(audited, operation, value):
    _state, session, recorder = audited
    before = dict((await session.execute(select(AuditTestItem.id, AuditTestItem.name))).all())
    expected = set(
        (await session.execute(select(AuditTestItem.id).where(AuditTestItem.value == value)))
        .scalars()
        .all()
    )
    stmt = operation(AuditTestItem).options(
        with_loader_criteria(AuditTestItem, AuditTestItem.value == value)
    )
    if operation is update:
        stmt = stmt.values(name="changed")
    result = await session.execute(stmt)
    after = dict((await session.execute(select(AuditTestItem.id, AuditTestItem.name))).all())
    changed = {pk for pk, name in before.items() if after.get(pk) != name}
    assert changed == expected
    assert result.rowcount == len(expected)
    assert {r.entity_id for r in recorder.records} == {str(pk) for pk in changed}
    assert len(recorder.records) == len(changed)
    assert all(
        r.action == ("bulk_updated" if operation is update else "bulk_deleted")
        for r in recorder.records
    )


@pytest.mark.parametrize("operation", [update, delete], ids=["update", "delete"])
async def test_bulk_audit_loader_criteria_keeps_execute_parameters(audited, operation):
    _state, session, recorder = audited
    target = (
        await session.execute(select(AuditTestItem.id).where(AuditTestItem.value == 2))
    ).scalar_one()
    stmt = (
        operation(AuditTestItem)
        .where(AuditTestItem.value >= 1)
        .options(
            with_loader_criteria(AuditTestItem, AuditTestItem.value == bindparam("wanted_value"))
        )
    )
    if operation is update:
        stmt = stmt.values(name="changed")
    result = await session.execute(stmt, {"wanted_value": 2})
    assert result.rowcount == 1
    assert [r.entity_id for r in recorder.records] == [str(target)]


@pytest.mark.parametrize("edit_title", [False, True])
async def test_orm_restore_records_lifecycle_and_concurrent_edits(audited, edit_title):
    _state, session, recorder = audited
    item = SoftDeleteItem(title="archived", is_deleted=True)
    session.add(item)
    await session.flush()
    recorder.records.clear()
    item.is_deleted = False
    if edit_title:
        item.title = "restored title"
    user_token = current_user_id.set("admin")
    correlation_token = correlation_id.set("restore-request")
    try:
        await session.flush()
    finally:
        current_user_id.reset(user_token)
        correlation_id.reset(correlation_token)
    [record] = recorder.records
    assert record.action == "restored"
    assert record.entity_type == "SoftDeleteItem"
    assert record.entity_id == str(item.id)
    assert record.user_id == "admin"
    assert record.correlation_id == "restore-request"
    assert record.changes == (
        [{"field": "title", "old": "archived", "new": "restored title"}] if edit_title else []
    )
    recorder.records.clear()
    item.title = "later edit"
    await session.flush()
    assert [r.action for r in recorder.records] == ["updated"]


async def test_orm_primary_key_update_records_old_and_new_key(audited):
    _state, session, recorder = audited
    item = (
        await session.execute(select(AuditTestItem).where(AuditTestItem.value == 1))
    ).scalar_one()
    old_id = item.id
    item.id = 999
    await session.flush()
    [record] = recorder.records
    assert record.action == "updated"
    assert record.entity_id == "999"
    assert record.changes == [{"field": "id", "old": old_id, "new": 999}]
    assert await session.get(AuditTestItem, old_id) is None
    assert await session.get(AuditTestItem, 999) is item
