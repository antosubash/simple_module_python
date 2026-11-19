"""Custom scopes share the built-in query paths and compose with tenancy."""

import pytest
import simple_module_db as db
from _workspace_scope_models import WsItem, workspace, workspace_db
from sqlalchemy import delete, func, insert, select, update

__all__ = ["workspace_db"]


def test_public_scope_api():
    assert callable(getattr(db, "register_scope", None))
    assert callable(getattr(db, "ScopeFilter", None))


@pytest.mark.parametrize("shape", ["orm", "count", "core", "subquery", "cte", "alias"])
def test_workspace_reads_and_counts(workspace_db, shape):
    table = WsItem.__table__
    stmts = {
        "orm": select(WsItem.id).order_by(WsItem.id),
        "count": select(func.count()).select_from(WsItem),
        "core": select(table.c.id).order_by(table.c.id),
        "subquery": select(func.count()).select_from(select(table).subquery()),
        "cte": select(func.count()).select_from(select(table).cte()),
        "alias": select(func.count()).select_from(table.alias()),
    }
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(stmts[shape]).scalars().all() == (
            [1, 5] if shape in {"orm", "core"} else [2]
        )


def test_bypasses_are_independent(workspace_db):
    stmt = select(WsItem.id).order_by(WsItem.id)
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(
            stmt.execution_options(all_workspaces=True)
        ).scalars().all() == [1, 2, 5]
        assert workspace_db.execute(stmt.execution_options(all_tenants=True)).scalars().all() == [
            1,
            3,
            5,
        ]
        assert workspace_db.execute(
            stmt.execution_options(include_deleted=True)
        ).scalars().all() == [1, 4, 5]
        assert workspace_db.execute(stmt).scalars().all() == [1, 5]


@pytest.mark.parametrize("core", [False, True])
@pytest.mark.parametrize("operation", ["select", "count", "update", "delete", "insert"])
def test_missing_workspace_fails_closed(workspace_db, core, operation):
    target = WsItem.__table__ if core else WsItem
    stmts = {
        "select": select(target),
        "count": select(func.count()).select_from(target),
        "update": update(target).values(name="changed"),
        "delete": delete(target),
        "insert": insert(target).values(id=20, workspace_id="w1"),
    }
    with db.tenant_context("a"), pytest.raises(db.ScopeIsolationError, match="workspace"):
        workspace_db.execute(stmts[operation])


@pytest.mark.parametrize("core", [False, True])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_workspace_dml_targets(workspace_db, core, operation):
    target = WsItem.__table__ if core else WsItem
    stmt = update(target).values(name="changed") if operation == "update" else delete(target)
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(stmt).rowcount == 3  # writes include trashed rows
    rows = (
        workspace_db.connection()
        .execute(select(WsItem.__table__).order_by(WsItem.id))
        .mappings()
        .all()
    )
    if operation == "update":
        assert [(r["id"], r["name"]) for r in rows] == [
            (1, "changed"),
            (2, "original"),
            (3, "original"),
            (4, "changed"),
            (5, "changed"),
        ]
    else:
        assert [r["id"] for r in rows] == [2, 3]


def test_context_changes_do_not_reuse_cached_value(workspace_db):
    stmt = select(WsItem.id).order_by(WsItem.id)
    with db.tenant_context("a"):
        for ctx, expected in [("w1", [1, 5]), ("w2", [2]), ("w1", [1, 5])]:
            with workspace(ctx):
                assert workspace_db.execute(stmt).scalars().all() == expected


def test_insert_stamping(workspace_db):
    with db.tenant_context("a"), workspace("w1"):
        obj = WsItem(id=20)
        workspace_db.add(obj)
        workspace_db.flush()
        assert (obj.workspace_id, obj.tenant_id) == ("w1", "a")
        workspace_db.execute(insert(WsItem), [{"id": 21}, {"id": 22}])
        assert (
            workspace_db.execute(select(WsItem.workspace_id).where(WsItem.id >= 20)).scalars().all()
            == ["w1"] * 3
        )


def test_bulk_pk_update_intersects_scopes(workspace_db):
    with db.tenant_context("a"), workspace("w1"):
        workspace_db.execute(
            update(WsItem),
            [
                {"id": 1, "name": "changed"},
                {"id": 2, "name": "changed"},
                {"id": 3, "name": "changed"},
            ],
        )
    table = WsItem.__table__
    assert workspace_db.connection().execute(
        select(table.c.id).where(table.c.name == "changed")
    ).scalars().all() == [1]
