"""Models and seed for the DML / INSERT shape tests (``test_db_dml_*``, ``test_db_insert_*``).

Tenant ``a`` owns doc 1 (live) and doc 4 (trashed); tenant ``b`` owns doc 2
(live), doc 3 (trashed) and its only ``Other`` row. ``Proj`` is untenanted.
"""

import pytest
from _models import _tenant_session
from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.tenancy import all_tenants, tenant_context
from sqlalchemy import event, select
from sqlmodel import Field

Base = create_module_base("dml_scope")


class ScopeProj(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "dml_scope_proj"
    id: int = Field(primary_key=True)
    note: str | None = None


class ScopeDoc(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "dml_scope_doc"
    id: int = Field(primary_key=True)
    name: str = "d"
    note: str | None = None


class ScopeOther(Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "dml_scope_other"
    id: int = Field(primary_key=True)
    name: str = "o"


doc, proj, other = ScopeDoc.__table__, ScopeProj.__table__, ScopeOther.__table__


async def seed(session):
    session.add_all([ScopeProj(id=1, note="p1"), ScopeProj(id=2, note="p2")])
    await session.flush()
    with tenant_context("a"):
        session.add_all([ScopeDoc(id=1, name="a-doc"), ScopeDoc(id=4, name="a-trash")])
        await session.flush()
    with tenant_context("b"):
        session.add_all([ScopeDoc(id=2, name="b-secret"), ScopeDoc(id=3, name="b-trash")])
        session.add(ScopeOther(id=1, name="b-other"))
        await session.flush()
    with all_tenants():
        for trashed in (await session.execute(select(ScopeDoc).where(ScopeDoc.id > 2))).scalars():
            trashed.is_deleted = True
        await session.flush()
    await session.commit()


@pytest.fixture
async def scope_db():
    """Strict mode on, as with ``multi_tenant``."""
    async for session in _tenant_session(Base.metadata, strict=True, seed=seed):
        yield session


@pytest.fixture
async def lax_db():
    """A single-tenant install: strict mode off."""
    async for session in _tenant_session(Base.metadata, strict=False, seed=seed):
        yield session


async def docs(session):
    """Every doc row as ``(id, tenant_id, name, note)``, bypassing both filters."""
    stmt = select(doc.c.id, doc.c.tenant_id, doc.c.name, doc.c.note).order_by(doc.c.id)
    stmt = stmt.execution_options(all_tenants=True, include_deleted=True)
    return [tuple(r) for r in (await session.execute(stmt)).all()]


async def projs(session):
    return [tuple(r) for r in (await session.execute(select(proj).order_by(proj.c.id))).all()]


@pytest.fixture
def captured_sql(scope_db):
    """The SQL statements ``scope_db``'s engine sends, in order."""
    found: list[str] = []
    engine = scope_db.bind.sync_engine

    def capture(conn, cursor, statement, params, context, executemany):
        found.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    yield found
    event.remove(engine, "before_cursor_execute", capture)
