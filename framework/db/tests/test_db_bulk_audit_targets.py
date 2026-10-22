"""Bulk audit reads only a statement's own targets, and catches every soft-delete shape (#557).

Regressions from the security review: excluded columns leaked through the
execute params, and an ``is_deleted`` write that was not literally ``True``
(SQL, a truthy int, an executemany row, a restore) went unrecorded and so
also escaped ``refuse_unaudited_dml``.
"""

from __future__ import annotations

import pytest
from _audit_models import AuditTestItem, PartialExcludeModel, SoftDeleteItem
from simple_module_db import UnauditedWriteError
from sqlalchemy import bindparam, select, true, update


async def _seed(session, recorder, *rows) -> list[int]:
    session.add_all(rows)
    await session.flush()
    recorder.records.clear()
    return [row.id for row in rows]


async def test_excluded_and_stray_params_never_reach_changes(audited):
    _state, session, recorder = audited
    await _seed(session, recorder, PartialExcludeModel(username="u"))
    stmt = update(PartialExcludeModel).values(username=bindparam("u"))
    await session.execute(stmt, {"u": "v", "password_hash": "leak", "extra": "leak"})
    assert [r.changes for r in recorder.records] == [[{"field": "username", "new": "v"}]]


async def test_excluded_only_writes_through_params_or_core_keys_are_skipped(audited):
    _state, session, recorder = audited
    (pid,) = await _seed(session, recorder, PartialExcludeModel(username="u"))
    table = PartialExcludeModel.__table__
    await session.execute(update(table).values({table.c.password_hash: "h"}))
    await session.execute(update(PartialExcludeModel), [{"id": pid, "password_hash": "h"}])
    assert recorder.records == []


async def test_a_column_param_beside_an_excluded_value_is_still_audited(audited):
    _state, session, recorder = audited
    await _seed(session, recorder, PartialExcludeModel(username="u"))
    stmt = update(PartialExcludeModel).values(password_hash=bindparam("p"))
    await session.execute(stmt, {"p": "h", "username": "hidden?"})
    rows = (await session.execute(select(PartialExcludeModel.username))).scalars().all()
    assert rows == ["hidden?"]  # SQLAlchemy writes it, so the trail must show it
    assert [r.changes for r in recorder.records] == [[{"field": "username", "new": "hidden?"}]]


@pytest.mark.parametrize(
    ("value", "params"),
    [(true(), None), (1, None), (bindparam("d"), {"d": True})],
    ids=["sql-true", "truthy-int", "bound-param"],
)
async def test_soft_delete_shapes_are_recorded(audited, value, params):
    _state, session, recorder = audited
    await _seed(session, recorder, SoftDeleteItem(title="t"))
    await session.execute(update(SoftDeleteItem).values(is_deleted=value), params)
    assert [r.action for r in recorder.records] == ["bulk_soft_deleted"]


async def test_executemany_soft_delete_and_restore(audited):
    _state, session, recorder = audited
    (sid,) = await _seed(session, recorder, SoftDeleteItem(title="t"))
    await session.execute(update(SoftDeleteItem), [{"id": sid, "is_deleted": True}])
    await session.execute(update(SoftDeleteItem), [{"id": sid, "is_deleted": False}])
    await session.execute(update(SoftDeleteItem).values(is_deleted=False))
    assert [r.action for r in recorder.records] == [
        "bulk_soft_deleted",
        "bulk_restored",
        "bulk_restored",
    ]


async def test_primary_key_change_is_recorded(audited):
    _state, session, recorder = audited
    (iid,) = await _seed(session, recorder, AuditTestItem(name="pk"))
    await session.execute(update(AuditTestItem).where(AuditTestItem.id == iid).values(id=9999))
    assert [(r.action, r.changes) for r in recorder.records] == [
        ("bulk_updated", [{"field": "id", "new": 9999}])
    ]


@pytest.mark.parametrize(
    "stmt",
    [
        update(SoftDeleteItem).values(is_deleted=true()),
        update(SoftDeleteItem).values(is_deleted=False),
        update(AuditTestItem).values(id=9999),
    ],
    ids=["soft-delete", "restore", "pk-change"],
)
async def test_strict_mode_refuses_flag_and_pk_writes(audited, stmt):
    state, session, _recorder = audited
    state.refuse_unaudited_dml = True
    with pytest.raises(UnauditedWriteError):
        await session.execute(stmt.execution_options(sm_audit=False))
