"""Models and seed data for the Core-statement scoping tests (#506).

Tenant A owns tags ``used`` (id 1) and ``unused`` (id 2) and one link to
``used``. Tenant B owns ``b-tag`` (id 3) and three links aimed at A's
``used`` tag — the leak probe: any shape that lets them through counts 4
links for ``used`` instead of 1. ``_Soft`` has a live and a trashed row
for ``used``; ``_Plain`` (no mixins) has ids 1 and 3.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.session import init_db
from simple_module_db.tenancy import current_tenant_id, tenant_context
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_URL = database_url_for_tests()
_Base = create_module_base("cscope")


class Tag(_Base, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "cscope_tag"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


class Link(_Base, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "cscope_link"
    id: int | None = Field(default=None, primary_key=True)
    tag_id: int | None = None
    article_id: int = 0


class Soft(_Base, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "cscope_soft"
    id: int | None = Field(default=None, primary_key=True)
    tag_id: int | None = None


class Plain(_Base, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "cscope_plain"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


tag, link, soft, plain = Tag.__table__, Link.__table__, Soft.__table__, Plain.__table__


async def _seed(session: AsyncSession) -> None:
    session.add_all([Plain(id=1, name="p1"), Plain(id=3, name="p3")])
    with tenant_context("A"):
        session.add_all([Tag(id=1, name="used"), Tag(id=2, name="unused")])
        session.add(Link(id=1, tag_id=1, article_id=1))
        session.add_all([Soft(id=1, tag_id=1), Soft(id=2, tag_id=1, is_deleted=True)])
        await session.flush()
    with tenant_context("B"):
        session.add(Tag(id=3, name="b-tag"))
        session.add_all([Link(id=n, tag_id=1, article_id=n) for n in (7, 8, 9)])
        await session.flush()
    await session.commit()


@pytest.fixture
async def seeded() -> AsyncGenerator[AsyncSession, None]:
    """A session acting as tenant A over the seeded rows."""
    state = init_db(_URL, **init_db_kwargs(_URL))
    try:
        register_listeners(state)
        await reset_schema(state.engine)
        async with state.engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        async with state.session_factory() as session:
            await _seed(session)
        async with state.session_factory() as session:
            token = current_tenant_id.set("A")
            try:
                yield session
            finally:
                current_tenant_id.reset(token)
    finally:
        await state.engine.dispose()


def make_strict(session: AsyncSession) -> None:
    """Strict isolation with no tenant bound: every Core reference must refuse."""
    bind_engine_policy(session.bind.sync_engine, EngineTenancy(tenant_strict=True))
    current_tenant_id.set(None)
