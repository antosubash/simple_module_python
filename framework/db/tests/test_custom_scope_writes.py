"""Workspace insert stamping and guards for writes outside the query path."""

import pytest
import simple_module_db as db
from _workspace_scope_models import WsItem, workspace, workspace_db
from sqlalchemy import bindparam, insert, literal, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

__all__ = ["workspace_db"]


@pytest.mark.parametrize("shape", ["orm", "core", "bulk", "multi", "from_select"])
def test_scalar_scope_stamps_insert_shapes(workspace_db, shape):
    table = WsItem.__table__
    stmts = {
        "orm": insert(WsItem).values(id=20),
        "core": insert(table).values(id=20),
        "bulk": insert(WsItem),
        "multi": insert(table).values([{"id": 20}, {"id": 21}]),
        "from_select": insert(table).from_select(["id"], select(literal(20))),
    }
    with db.tenant_context("a"), workspace("w1"):
        if shape == "bulk":
            workspace_db.execute(stmts[shape], [{"id": 20}, {"id": 21}])
        else:
            workspace_db.execute(stmts[shape])
        rows = workspace_db.execute(
            select(WsItem.workspace_id, WsItem.tenant_id).where(WsItem.id >= 20)
        ).all()
        assert rows == [("w1", "a")] * (2 if shape in {"bulk", "multi"} else 1)


@pytest.mark.parametrize(
    "shape", ["object", "values", "bulk", "multi", "from_select", "bind_override"]
)
def test_insert_rejects_foreign_workspace(workspace_db, shape):
    with db.tenant_context("a"), workspace("w1"), pytest.raises(db.ScopeIsolationError):
        if shape == "object":
            workspace_db.add(WsItem(id=20, workspace_id="w2"))
            workspace_db.flush()
        elif shape == "values":
            workspace_db.execute(insert(WsItem).values(id=20, workspace_id="w2"))
        elif shape == "bulk":
            workspace_db.execute(insert(WsItem), [{"id": 20, "workspace_id": "w2"}])
        elif shape == "multi":
            workspace_db.execute(
                insert(WsItem.__table__).values([{"id": 20, "workspace_id": "w2"}])
            )
        elif shape == "from_select":
            workspace_db.execute(
                insert(WsItem).from_select(
                    ["id", "workspace_id"], select(literal(20), literal("w2"))
                )
            )
        else:
            workspace_db.execute(
                insert(WsItem).values(id=20, workspace_id=bindparam("ws")), {"ws": "w2"}
            )


def test_flush_without_context_fails_closed(workspace_db):
    with db.tenant_context("a"), pytest.raises(db.ScopeIsolationError):
        workspace_db.add(WsItem(id=20, workspace_id="w1"))
        workspace_db.flush()


@pytest.mark.parametrize("operation", ["update", "delete", "move"])
def test_flush_checks_workspace_ownership(workspace_db, operation):
    with db.tenant_context("a"), workspace("w1"):
        obj = workspace_db.get(WsItem, 1)
    with db.tenant_context("a"), workspace("w2"), pytest.raises(db.ScopeIsolationError):
        if operation == "delete":
            workspace_db.delete(obj)
        elif operation == "move":
            obj.workspace_id = "w2"
        else:
            obj.name = "changed"
        workspace_db.flush()


def test_bulk_update_synchronizes_only_matching_workspace(workspace_db):
    with db.tenant_context("a"), workspace("w1"):
        loaded = (
            workspace_db.execute(select(WsItem).execution_options(all_workspaces=True))
            .scalars()
            .all()
        )
        workspace_db.execute(update(WsItem), [{"id": r.id, "name": "changed"} for r in loaded])
        assert [(r.id, r.name) for r in loaded] == [(1, "changed"), (2, "original"), (5, "changed")]


def test_upsert_cannot_update_foreign_workspace(workspace_db):
    stmt = sqlite_insert(WsItem).values(id=2, name="changed")
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={"name": "changed"})
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(stmt).rowcount == 0


def test_scope_column_update_requires_bypass(workspace_db):
    stmt = update(WsItem).where(WsItem.id == 1).values(workspace_id="w2")
    with db.tenant_context("a"), workspace("w1"):
        with pytest.raises(db.ScopeIsolationError):
            workspace_db.execute(stmt)
        assert workspace_db.execute(stmt.execution_options(all_workspaces=True)).rowcount == 1


@pytest.mark.parametrize(
    "method", ["bulk_save_objects", "bulk_insert_mappings", "bulk_update_mappings"]
)
def test_legacy_bulk_cannot_escape_custom_scope(workspace_db, method):
    with db.all_tenants(), workspace("w1"), pytest.raises(db.ScopeIsolationError):
        if method == "bulk_save_objects":
            workspace_db.bulk_save_objects([WsItem(id=20, tenant_id="a", workspace_id="w2")])
        else:
            getattr(workspace_db, method)(
                WsItem, [{"id": 2, "name": "changed", "workspace_id": "w2"}]
            )
