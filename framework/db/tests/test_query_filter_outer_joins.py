"""The tenant / soft-delete filter keeps ORM outer joins outer (GH #417).

A column of the outer-joined table that only appears inside a function
(``func.count(Child.id)``) loses its ORM annotation, so the child looked like
a raw Core table and got a ``WHERE child.tenant_id = :t`` on top of the
``ON`` criteria — turning the LEFT JOIN into an inner one and dropping every
parent without children.

Tenant B's links point at tenant A's ``used`` tag: if the child's predicate
ever went missing from both ``ON`` and ``WHERE``, A's count would read 4.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import current_tenant_id, register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.session import init_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import Field

_TagBase = create_module_base("qfoj_tag")
_LinkBase = create_module_base("qfoj_link")
_SoftBase = create_module_base("qfoj_soft")
_PlainBase = create_module_base("qfoj_plain")


class _Tag(_TagBase, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfoj_tag_tag"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


class _TagLink(_LinkBase, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfoj_link_tag_link"
    id: int | None = Field(default=None, primary_key=True)
    tag_id: int | None = None  # no FK: each model has its own MetaData
    article_id: int = 0


class _SoftLink(_SoftBase, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfoj_soft_soft_link"
    id: int | None = Field(default=None, primary_key=True)
    tag_id: int | None = None  # no FK: each model has its own MetaData


class _Plain(_PlainBase, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Neither tenant-scoped nor soft-deletable: a FULL join's left side with no filter."""

    __tablename__ = "qfoj_plain_plain"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)


@pytest.fixture
async def seeded() -> AsyncGenerator[AsyncSession, None]:
    db_state = init_db("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            for base in (_TagBase, _LinkBase, _SoftBase, _PlainBase):
                await conn.run_sync(base.metadata.create_all)
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            used, unused = _Tag(name="used"), _Tag(name="unused")
            session.add_all([used, unused])
            await session.flush()
            session.add(_TagLink(tag_id=used.id, article_id=1))
            # Same id as ``used``: every link and soft link points at it too.
            session.add(_Plain(id=used.id, name="p1"))
            session.add_all([_SoftLink(tag_id=used.id), _SoftLink(tag_id=used.id, is_deleted=True)])
            await session.flush()
            current_tenant_id.reset(token)
            token = current_tenant_id.set("B")
            session.add(_Tag(name="b-tag"))
            # The leak probe: tenant B's links aimed at tenant A's tag.
            session.add_all([_TagLink(tag_id=used.id, article_id=n) for n in (7, 8, 9)])
            await session.flush()
            current_tenant_id.reset(token)
            await session.commit()
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            try:
                yield session
            finally:
                current_tenant_id.reset(token)
    finally:
        await db_state.engine.dispose()


COUNT_SHAPES = {
    "entity+count": lambda: (
        select(_Tag, func.count(_TagLink.article_id))
        .outerjoin(_TagLink, _TagLink.tag_id == _Tag.id)
        .group_by(_Tag.id)
    ),
    "columns+count, select_from": lambda: (
        select(_Tag.name, func.count(_TagLink.article_id))
        .select_from(_Tag)
        .outerjoin(_TagLink, _TagLink.tag_id == _Tag.id)
        .group_by(_Tag.name)
    ),
    "entity+entity": lambda: select(_Tag, _TagLink).outerjoin(_TagLink, _TagLink.tag_id == _Tag.id),
    "entity+column": lambda: select(_Tag, _TagLink.article_id).outerjoin(
        _TagLink, _TagLink.tag_id == _Tag.id
    ),
}


@pytest.mark.parametrize("shape", list(COUNT_SHAPES))
async def test_outer_join_keeps_the_unused_parent(seeded, shape):
    rows = (await seeded.execute(COUNT_SHAPES[shape]())).all()
    names = {r[0] if isinstance(r[0], str) else r[0].name for r in rows}
    assert names == {"used", "unused"}


async def test_outer_join_count_never_sees_other_tenants(seeded):
    """Review focus 1: tenant B's links point at A's tag; A's count stays 1."""
    rows = dict((await seeded.execute(COUNT_SHAPES["columns+count, select_from"]())).all())
    assert rows == {"used": 1, "unused": 0}


async def test_outer_join_entity_count_never_sees_other_tenants(seeded):
    stmt = COUNT_SHAPES["entity+count"]()
    rows = {t.name: n for t, n in (await seeded.execute(stmt)).all()}
    assert rows == {"used": 1, "unused": 0}


async def test_outer_join_from_keeps_the_parent_and_isolates(seeded):
    """``outerjoin_from`` records its target in ``_setup_joins`` the same way."""
    stmt = (
        select(_Tag.name, func.count(_TagLink.article_id))
        .outerjoin_from(_Tag, _TagLink, _TagLink.tag_id == _Tag.id)
        .group_by(_Tag.name)
    )
    assert dict((await seeded.execute(stmt)).all()) == {"used": 1, "unused": 0}


async def test_inner_join_still_filters_the_child(seeded):
    stmt = (
        select(_Tag.name, func.count(_TagLink.article_id))
        .join(_TagLink, _TagLink.tag_id == _Tag.id)
        .group_by(_Tag.name)
    )
    assert dict((await seeded.execute(stmt)).all()) == {"used": 1}


async def test_raw_table_outer_join_stays_filtered(seeded):
    """A Core table target gets no ON criteria, so it keeps the WHERE predicate (no leak)."""
    link = _TagLink.__table__
    stmt = (
        select(_Tag.name, func.count(link.c.article_id))
        .select_from(_Tag)
        .outerjoin(link, link.c.tag_id == _Tag.id)
        .group_by(_Tag.name)
    )
    rows = dict((await seeded.execute(stmt)).all())
    assert rows.get("used") == 1  # never 4 (tenant B's links)


async def test_raw_column_of_orm_outer_target_never_sees_other_tenants(seeded):
    """``Model.__table__.c.x`` beside an ORM outer join is that join's own FROM.

    The un-annotated reference renders as the same ``FROM`` occurrence the
    ORM join put its ``ON`` criteria on, so dropping its ``WHERE`` cannot let
    tenant B's links through.
    """
    link = _TagLink.__table__
    stmt = (
        select(_Tag.name, link.c.article_id)
        .select_from(_Tag)
        .outerjoin(_TagLink, _TagLink.tag_id == _Tag.id)
    )
    assert sorted((await seeded.execute(stmt)).all()) == [("unused", None), ("used", 1)]


async def test_soft_deleted_outer_child_keeps_the_parent(seeded):
    stmt = (
        select(_Tag.name, func.count(_SoftLink.id))
        .select_from(_Tag)
        .outerjoin(_SoftLink, _SoftLink.tag_id == _Tag.id)
        .group_by(_Tag.name)
    )
    assert dict((await seeded.execute(stmt)).all()) == {"used": 1, "unused": 0}


@pytest.mark.xfail(strict=True, reason="pre-existing: Core outer join right side unfiltered")
async def test_core_outer_join_right_side_is_tenant_filtered(seeded):
    """A pure Core ``tag.outerjoin(link)`` gets no ``ON`` criteria and no ``WHERE``.

    ``_where_able`` keeps the nullable side out of ``WHERE`` (correctly), but
    nothing else filters a Core table, so ``count(*)`` counts tenant B's links.
    """
    tag, link = _Tag.__table__, _TagLink.__table__
    stmt = (
        select(tag.c.name, func.count())
        .select_from(tag.outerjoin(link, link.c.tag_id == tag.c.id))
        .group_by(tag.c.name)
    )
    assert dict((await seeded.execute(stmt)).all()) == {"used": 1, "unused": 1}


async def test_strict_mode_without_tenant_still_refuses_an_outer_child(seeded):
    """The ``ON``-covered exclusion needs a bound tenant; strict mode keeps refusing."""
    from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
    from simple_module_db.tenancy import TenantIsolationError

    bind_engine_policy(seeded.bind.sync_engine, EngineTenancy(tenant_strict=True))
    current_tenant_id.set(None)
    # Neither selected entity is tenant-scoped (a raw column names no mapper),
    # so only the child's would-be WHERE predicate makes this a refusal
    # rather than a silent empty join.
    link = _TagLink.__table__
    stmt = (
        select(_SoftLink.id, link.c.article_id)
        .select_from(_SoftLink)
        .outerjoin(_TagLink, _TagLink.tag_id == _SoftLink.tag_id)
    )
    with pytest.raises(TenantIsolationError):
        await seeded.execute(stmt)


async def test_full_join_never_returns_other_tenants_children(seeded):
    """A FULL join preserves its right side: ON cannot filter it, WHERE must.

    Tenant B's links fail the ON predicate and would come back as unmatched
    ``(None, …)`` rows if the child's WHERE predicate were dropped.
    """
    stmt = (
        select(_Plain.name, func.count(_TagLink.id))
        .select_from(_Plain)
        .outerjoin(_TagLink, _TagLink.tag_id == _Plain.id, full=True)
        .group_by(_Plain.name)
    )
    assert (await seeded.execute(stmt)).all() == [("p1", 1)]


async def test_full_join_never_returns_trashed_children(seeded):
    stmt = (
        select(_Plain.name, func.count(_SoftLink.id))
        .select_from(_Plain)
        .outerjoin(_SoftLink, _SoftLink.tag_id == _Plain.id, full=True)
        .group_by(_Plain.name)
    )
    assert (await seeded.execute(stmt)).all() == [("p1", 1)]
