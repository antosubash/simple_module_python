"""Registration and context boundaries must not silently disable custom policies."""

from contextvars import ContextVar

import pytest
import simple_module_db as db
from _scope_inheritance_models import InheritanceBase, ScopeAnimal, ScopeDog
from _workspace_scope_models import WsItem, WsLink, WsParent, workspace, workspace_db
from sqlalchemy import inspect, select, true
from sqlalchemy.orm import joinedload, selectinload, subqueryload

__all__ = ["workspace_db"]


def test_contextvar_default_and_falsey_context(workspace_db):
    bound = ContextVar("subset_limit", default=1)
    db.register_scope(
        db.ScopeFilter(
            name="subset",
            applies_to=lambda m: m.class_ is WsItem,
            criteria=lambda cls, ctx: cls.id <= ctx,
            context=bound,
            bypass_option="all_subset",
            fail_closed=False,
        )
    )
    with db.tenant_context("a"), workspace("w1"):
        assert workspace_db.execute(select(WsItem.id)).scalars().all() == [1]
        token = bound.set(0)
        try:
            assert workspace_db.execute(select(WsItem.id)).scalars().all() == []
        finally:
            bound.reset(token)
        token = bound.set(None)
        try:
            assert workspace_db.execute(select(WsItem.id)).scalars().all() == [1, 5]
        finally:
            bound.reset(token)


def test_missing_context_never_uses_permissive_predicate(workspace_db):
    db.register_scope(
        db.ScopeFilter(
            name="missing_link",
            applies_to=lambda m: m.class_ is WsLink,
            criteria=lambda cls, ctx: true(),
            context=ContextVar("missing_link_context"),
            bypass_option="all_missing_links",
            column="workspace_id",
        )
    )
    with db.tenant_context("a"), workspace("w1"):
        parent = (
            workspace_db.execute(select(WsParent).options(joinedload(WsParent.linked)))
            .unique()
            .scalar_one()
        )
        assert parent.linked == []


def test_secondary_scope_registered_after_mapper_configuration(workspace_db):
    inspect(WsParent).registry.configure()
    db.register_scope(
        db.ScopeFilter(
            name="late_link",
            applies_to=lambda m: m.class_ is WsLink,
            criteria=lambda cls, ctx: cls.workspace_id == ctx,
            context=lambda: "w2",
            bypass_option="all_late_links",
            column="workspace_id",
        )
    )
    with db.tenant_context("a"), workspace("w1"):
        stmt = select(WsParent).options(joinedload(WsParent.linked))
        parent = (
            workspace_db.execute(stmt.execution_options(all_workspaces=True)).unique().scalar_one()
        )
        assert [r.id for r in parent.linked] == [5]


def test_duplicate_names_cannot_replace_policy(workspace_db):
    with pytest.raises(ValueError, match="already registered"):
        db.register_scope(
            db.ScopeFilter(
                name="workspace",
                applies_to=lambda m: True,
                criteria=lambda cls, ctx: true(),
                context=lambda: True,
                bypass_option="all_workspaces",
            )
        )


@pytest.mark.parametrize("loader", [joinedload, selectinload, subqueryload])
def test_secondary_predicate_does_not_require_stamp_column(workspace_db, loader):
    db.register_scope(
        db.ScopeFilter(
            name="no_column_link",
            applies_to=lambda m: m.class_ is WsLink,
            criteria=lambda cls, ctx: cls.workspace_id == ctx,
            context=lambda: "w1",
            bypass_option="all_no_column_links",
        )
    )
    with db.tenant_context("a"), workspace("w1"):
        stmt = (
            select(WsParent).options(loader(WsParent.linked)).execution_options(all_workspaces=True)
        )
        parent = workspace_db.execute(stmt).unique().scalar_one()
        assert [r.id for r in parent.linked] == [1]


def test_late_registration_includes_single_table_subclass(workspace_db):
    InheritanceBase.metadata.create_all(workspace_db.bind)
    inspect(ScopeAnimal).registry.configure()
    workspace_db.connection().execute(
        ScopeAnimal.__table__.insert(),
        [
            {"id": 1, "kind": "dog", "owner": "visible"},
            {"id": 2, "kind": "dog", "owner": "foreign"},
        ],
    )
    db.register_scope(
        db.ScopeFilter(
            name="animal_owner",
            applies_to=lambda m: m.class_ is ScopeDog,
            criteria=lambda cls, ctx: cls.owner == ctx,
            context=lambda: "visible",
            bypass_option="all_owners",
        )
    )
    assert workspace_db.execute(select(ScopeDog.id)).scalars().all() == [1]
