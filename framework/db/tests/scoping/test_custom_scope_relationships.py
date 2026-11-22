"""Workspace predicates reach loader-built links and survive compiled statement reuse."""

import pytest
import simple_module_db as db
from _workspace_scope_models import WsItem, WsParent, workspace, workspace_db
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload, selectinload, subqueryload

__all__ = ["workspace_db"]


@pytest.mark.parametrize("relationship_name", ["kids", "linked"])
@pytest.mark.parametrize("loader", ["lazy", "joined", "selectin", "subquery"])
def test_relationship_loaders(workspace_db, relationship_name, loader):
    relation = getattr(WsParent, relationship_name)
    stmt = select(WsParent)
    if loader != "lazy":
        stmt = stmt.options(
            {"joined": joinedload, "selectin": selectinload, "subquery": subqueryload}[loader](
                relation
            )
        )
    with db.tenant_context("a"), workspace("w1"):
        parent = workspace_db.execute(stmt).unique().scalar_one()
        assert [r.id for r in getattr(parent, relationship_name)] == (
            [1, 5] if relationship_name == "kids" else [1]
        )


@pytest.mark.parametrize("loader", [joinedload, selectinload, subqueryload])
def test_secondary_bypass_is_bound_per_execution(workspace_db, loader):
    stmt = select(WsParent).options(loader(WsParent.linked))
    with db.tenant_context("a"), workspace("w1"):
        for bypass, expected in [(False, [1]), (True, [1, 5]), (False, [1])]:
            workspace_db.expunge_all()
            parent = (
                workspace_db.execute(stmt.execution_options(all_workspaces=bypass))
                .unique()
                .scalar_one()
            )
            assert [r.id for r in parent.linked] == expected


def test_secondary_join_any_and_count(workspace_db):
    with db.tenant_context("a"), workspace("w1"):
        stmt = select(WsItem.id).join(WsParent.linked)
        assert workspace_db.execute(stmt).scalars().all() == [1]
        assert (
            workspace_db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            == 1
        )
        assert (
            workspace_db.execute(
                select(WsParent.id).where(WsParent.linked.any(WsItem.id == 5))
            ).all()
            == []
        )
        # A target in this workspace linked through another workspace is invisible.
        assert (
            workspace_db.execute(
                delete(WsParent).where(WsParent.linked.any(WsItem.id == 5))
            ).rowcount
            == 0
        )


def test_registration_after_mapper_configuration(workspace_db):
    # workspace_db has mapped/configured the classes already. A mapper predicate
    # and callable context must work without touching private registry sets.
    from sqlalchemy import inspect

    inspect(WsItem).registry.configure()
    db.register_scope(
        db.ScopeFilter(
            name="workspace_subset",
            applies_to=lambda mapper: mapper.class_ is WsItem,
            criteria=lambda cls, ctx: cls.id <= ctx,
            context=lambda: 1,
            bypass_option="all_subset_items",
        )
    )
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(select(WsItem.id)).scalars().all() == [1]
        assert workspace_db.execute(
            select(WsItem.id).execution_options(all_subset_items=True)
        ).scalars().all() == [1, 5]
