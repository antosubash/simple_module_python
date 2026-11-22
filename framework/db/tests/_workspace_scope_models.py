"""Workspace fixtures: overlapping tenant/workspace ownership and foreign links."""

from contextlib import contextmanager
from contextvars import ContextVar

import pytest
import simple_module_db as db
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session, relationship
from sqlmodel import Field, Relationship, SQLModel

Base = db.create_module_base("workspace_scope")
workspace_id = ContextVar("test_workspace_id", default=None)


class WorkspaceMixin(SQLModel):
    workspace_id: str | None = Field(default=None, nullable=False)


class WsParent(Base, WorkspaceMixin, db.MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "workspace_scope_parent"
    id: int = Field(primary_key=True)
    kids: list["WsItem"] = Relationship(
        sa_relationship=relationship("WsItem", viewonly=True, order_by="WsItem.id")
    )
    linked: list["WsItem"] = Relationship(
        sa_relationship=relationship(
            "WsItem",
            secondary=lambda: WsLink.__table__,
            primaryjoin="WsParent.id == WsLink.parent_id",
            secondaryjoin="WsLink.item_id == WsItem.id",
            viewonly=True,
            order_by="WsItem.id",
        )
    )


class WsItem(Base, WorkspaceMixin, db.MultiTenantMixin, db.SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "workspace_scope_item"
    id: int = Field(primary_key=True)
    name: str = "original"
    parent_id: int | None = Field(default=None, foreign_key="workspace_scope_parent.id")


class WsLink(Base, WorkspaceMixin, db.MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "workspace_scope_link"
    id: int = Field(primary_key=True)
    parent_id: int = Field(foreign_key="workspace_scope_parent.id")
    item_id: int = Field(foreign_key="workspace_scope_item.id")


@contextmanager
def workspace(value):
    token = workspace_id.set(value)
    try:
        yield
    finally:
        workspace_id.reset(token)


def stamp_workspace(obj, value):
    if obj.workspace_id is None:
        obj.workspace_id = value


@pytest.fixture
def workspace_db(monkeypatch):
    from simple_module_db.models.listeners import attach_session_listeners
    from simple_module_db.scoping import scopes
    from simple_module_db.scoping.query_filter import EngineTenancy, bind_engine_policy

    monkeypatch.setattr(scopes, "_scopes", dict(scopes._scopes))
    db.register_scope(
        db.ScopeFilter(
            name="workspace",
            applies_to=WorkspaceMixin,
            criteria=lambda cls, ctx: cls.workspace_id == ctx,
            context=workspace_id,
            bypass_option="all_workspaces",
            fail_closed=True,
            column="workspace_id",
            stamp=stamp_workspace,
        )
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(WsParent.__table__), [{"id": 10, "tenant_id": "a", "workspace_id": "w1"}]
        )
        conn.execute(
            insert(WsItem.__table__),
            [
                {"id": i, "tenant_id": t, "workspace_id": w, "is_deleted": d, "parent_id": 10}
                for i, t, w, d in [
                    (1, "a", "w1", False),
                    (2, "a", "w2", False),
                    (3, "b", "w1", False),
                    (4, "a", "w1", True),
                    (5, "a", "w1", False),
                ]
            ],
        )
        conn.execute(
            insert(WsLink.__table__),
            [
                {"id": 1, "parent_id": 10, "item_id": 1, "tenant_id": "a", "workspace_id": "w1"},
                {"id": 2, "parent_id": 10, "item_id": 5, "tenant_id": "a", "workspace_id": "w2"},
            ],
        )

    class WorkspaceSession(Session):
        pass

    attach_session_listeners(WorkspaceSession)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=True))
    try:
        with WorkspaceSession(engine) as session:
            yield session
    finally:
        engine.dispose()
