"""Relationship-path outer joins stay outer under the tenant filter (GH #417).

``.outerjoin(Parent.kids)`` records the relationship attribute, not the child
entity, as the join target. The child's loader criteria still render into the
join's ``ON``, so a ``WHERE child.tenant_id = :t`` on top of it (added because
``func.count(Child.id)`` strips the ORM annotation) turned the LEFT JOIN into
an inner one and dropped every parent without children.

Tenant B's kids (and B's association rows) point at tenant A's ``used``
parent: if the child's predicate went missing from both ``ON`` and ``WHERE``,
A's count would read 4.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db.base import create_module_base
from simple_module_db.listeners import current_tenant_id, register_listeners
from simple_module_db.mixins import MultiTenantMixin
from simple_module_db.session import init_db
from sqlalchemy import Column, ForeignKey, Integer, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, relationship
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Relationship

_RjBase = create_module_base("qfrj")

# Plain association table (no tenant column): only the child behind it is scoped.
_rj_assoc = Table(
    "qfrj_parent_kid",
    _RjBase.metadata,
    Column("parent_id", Integer, ForeignKey("qfrj_parent.id"), primary_key=True),
    Column("kid_id", Integer, ForeignKey("qfrj_kid.id"), primary_key=True),
)


class _RjParent(_RjBase, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfrj_parent"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)
    kids: list[_RjKid] = Relationship(sa_relationship=relationship("_RjKid", viewonly=True))
    linked: list[_RjKid] = Relationship(
        sa_relationship=relationship("_RjKid", secondary=_rj_assoc, viewonly=True)
    )


class _RjKid(_RjBase, MultiTenantMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    __tablename__ = "qfrj_kid"
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="qfrj_parent.id")


@pytest.fixture
async def seeded() -> AsyncGenerator[AsyncSession, None]:
    db_state = init_db("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_RjBase.metadata.create_all)
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            used, unused = _RjParent(name="used"), _RjParent(name="unused")
            session.add_all([used, unused])
            await session.flush()
            kid = _RjKid(parent_id=used.id)
            session.add(kid)
            await session.flush()
            current_tenant_id.reset(token)
            token = current_tenant_id.set("B")
            # The leak probe: tenant B's kids aimed at tenant A's parent.
            b_kids = [_RjKid(parent_id=used.id) for _ in range(3)]
            session.add_all(b_kids)
            await session.flush()
            current_tenant_id.reset(token)
            rows = [{"parent_id": used.id, "kid_id": k.id} for k in (kid, *b_kids)]
            await session.execute(_rj_assoc.insert(), rows)
            await session.commit()
        async with db_state.session_factory() as session:
            token = current_tenant_id.set("A")
            try:
                yield session
            finally:
                current_tenant_id.reset(token)
    finally:
        await db_state.engine.dispose()


def _counted(join_target, **kw):
    return (
        select(_RjParent.name, func.count(_RjKid.id))
        .select_from(_RjParent)
        .outerjoin(join_target, **kw)
        .group_by(_RjParent.name)
    )


async def test_relationship_outer_join_keeps_the_unused_parent(seeded):
    rows = dict((await seeded.execute(_counted(_RjParent.kids))).all())
    assert rows == {"used": 1, "unused": 0}


async def test_relationship_of_type_outer_join_keeps_the_unused_parent(seeded):
    rows = dict((await seeded.execute(_counted(_RjParent.kids.of_type(_RjKid)))).all())
    assert rows == {"used": 1, "unused": 0}


async def test_relationship_outer_join_entity_count_never_sees_other_tenants(seeded):
    stmt = select(_RjParent, func.count(_RjKid.id)).outerjoin(_RjParent.kids).group_by(_RjParent.id)
    rows = {p.name: n for p, n in (await seeded.execute(stmt)).all()}
    assert rows == {"used": 1, "unused": 0}


async def test_relationship_outer_join_puts_the_tenant_in_on(seeded):
    """Dropping the child's WHERE is only safe because its predicate sits in ON."""
    for target in (_RjParent.kids, _RjParent.kids.of_type(_RjKid)):
        raw = await seeded.run_sync(lambda s, t=target: _compiled_sql(s, _counted(t)))
        sql = " ".join(raw.split())
        joined, _, where = sql.partition(" LEFT OUTER JOIN ")[2].partition(" WHERE ")
        assert "qfrj_kid.tenant_id" in joined
        assert "qfrj_kid.tenant_id" not in where


def _compiled_sql(session, stmt) -> str:
    """The SQL the filter actually emits, captured from the ORM execute path."""
    from sqlalchemy import event

    seen: list[str] = []
    engine = session.get_bind()

    def capture(conn, cursor, statement, *_):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        session.execute(stmt).all()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    return seen[-1]


async def test_secondary_relationship_outer_join_stays_filtered(seeded):
    """An association table has no ON guarantee: the child keeps its WHERE (no leak)."""
    rows = dict((await seeded.execute(_counted(_RjParent.linked))).all())
    assert rows.get("used") == 1  # never 4 (tenant B's kids)


async def test_aliased_of_type_outer_join_stays_filtered(seeded):
    kid = aliased(_RjKid)
    stmt = (
        select(_RjParent.name, func.count(kid.id))
        .select_from(_RjParent)
        .outerjoin(_RjParent.kids.of_type(kid))
        .group_by(_RjParent.name)
    )
    rows = dict((await seeded.execute(stmt)).all())
    assert rows.get("used") == 1


async def test_full_relationship_join_never_returns_other_tenants_kids(seeded):
    """FULL preserves the right side: ON cannot filter it, so WHERE stays."""
    rows = (await seeded.execute(_counted(_RjParent.kids, full=True))).all()
    assert rows == [("used", 1)]
