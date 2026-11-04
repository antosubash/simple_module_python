"""Models and seed for the read-scope tests (relationship loaders, aliased entities).

Parent 1 belongs to tenant ``a``. Its children (``parent_id = 1``): 1 and 2
(``a``), 3 (``a``, trashed) and 4 (``b``). Its link rows (``secondary``):
1 → child 1 (``a``), 2 → child 2 (``b``) and 3 → child 2 (``a``, trashed).
"""

from collections.abc import Iterator

import pytest
from _models import _tenant_session
from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.tenancy import all_tenants, tenant_context
from sqlalchemy import event, update
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship

Base = create_module_base("read_scope")


class RsParent(Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "read_scope_parent"
    id: int = Field(primary_key=True)
    kids: list["RsChild"] = Relationship(
        sa_relationship=relationship("RsChild", viewonly=True, order_by="RsChild.id")
    )
    linked: list["RsChild"] = Relationship(
        sa_relationship=relationship(
            "RsChild",
            secondary=lambda: RsLink.__table__,
            primaryjoin="RsParent.id == RsLink.parent_id",
            secondaryjoin="RsLink.child_id == RsChild.id",
            viewonly=True,
            order_by="RsChild.id",
        )
    )


class RsChild(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "read_scope_child"
    id: int = Field(primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="read_scope_parent.id")


class RsLink(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "read_scope_link"
    id: int = Field(primary_key=True)
    parent_id: int = Field(foreign_key="read_scope_parent.id")
    child_id: int = Field(foreign_key="read_scope_child.id")


class RsProj(Base, table=True):  # ty: ignore[unsupported-base]
    """Untenanted, for ``aliased(RsProj, <subquery>)``."""

    __tablename__ = "read_scope_proj"
    id: int = Field(primary_key=True)
    child_id: int | None = None


parent, child, link, proj = (
    RsParent.__table__,
    RsChild.__table__,
    RsLink.__table__,
    RsProj.__table__,
)


async def seed(session):
    session.add_all([RsProj(id=1, child_id=1), RsProj(id=4, child_id=4)])
    with tenant_context("a"):
        session.add(RsParent(id=1))
        await session.flush()
        session.add_all([RsChild(id=i, parent_id=1) for i in (1, 2, 3)])
        await session.flush()
        session.add_all(
            [RsLink(id=1, parent_id=1, child_id=1), RsLink(id=3, parent_id=1, child_id=2)]
        )
        await session.flush()
    with tenant_context("b"):
        session.add(RsChild(id=4, parent_id=1))
        await session.flush()
        session.add(RsLink(id=2, parent_id=1, child_id=2))
        await session.flush()
    with all_tenants():
        await session.execute(update(child).where(child.c.id == 3).values(is_deleted=True))
        await session.execute(update(link).where(link.c.id == 3).values(is_deleted=True))
    await session.commit()


@pytest.fixture
async def read_db():
    """Strict mode on, as with ``multi_tenant``."""
    async for session in _tenant_session(Base.metadata, strict=True, seed=seed):
        yield session


@pytest.fixture
async def lax_read_db():
    """A single-tenant install: strict mode off."""
    async for session in _tenant_session(Base.metadata, strict=False, seed=seed):
        yield session


@pytest.fixture
def read_sql(read_db) -> Iterator[list[tuple[str, object]]]:
    """Every ``(statement, params)`` sent to ``read_db``'s engine while the test runs."""
    seen: list[tuple[str, object]] = []
    engine = read_db.bind.sync_engine

    def capture(conn, cursor, statement, params, context, executemany):
        seen.append((statement, params))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", capture)
