"""``aliased(Model, <join>)`` and ``aliased(Model, <text>)``: allowed only where scoped.

A join that reads only the entity's own table besides unscoped ones is
filtered by the entity's loader criteria; any other scoped table in it is
refused like other Core reads. SQL text under an entity of a scoped table
is refused outright: no filter can read it. Both run under ``all_tenants()``
(with ``include_deleted=True``).
"""

import pytest
from _db_read_scope_models import RsChild, RsProj, child, proj, read_db
from simple_module_db._entity_selectables import _own_join_only, _own_rows_only
from simple_module_db.tenancy import TenantIsolationError, all_tenants, tenant_context
from sqlalchemy import ForeignKey, Integer, String, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, aliased, mapped_column, with_polymorphic
from sqlalchemy.sql.selectable import Join

__all__ = ["read_db"]


def _child_text():
    names = ", ".join(c.name for c in child.c)
    return text(f"SELECT {names} FROM read_scope_child").columns(*child.c)


async def test_own_table_joined_to_an_unscoped_table_is_scoped(read_db):
    child_alias = aliased(RsChild, child.join(proj, proj.c.child_id == child.c.id))
    with tenant_context("a"):
        assert (await read_db.execute(select(child_alias.id))).scalars().all() == [1]
    with tenant_context("b"):
        assert (await read_db.execute(select(child_alias.id))).scalars().all() == [4]


async def test_join_reading_another_scoped_table_is_refused(read_db):
    proj_alias = aliased(RsProj, proj.join(child, proj.c.child_id == child.c.id))
    with tenant_context("a"), pytest.raises(TenantIsolationError, match="read_scope_child"):
        await read_db.execute(select(proj_alias.id))


async def test_own_table_joined_to_its_own_alias_is_refused(read_db):
    other = child.alias("other")
    child_alias = aliased(RsChild, child.join(other, other.c.id == child.c.parent_id))
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await read_db.execute(select(child_alias.id))


async def test_refused_join_runs_under_all_tenants_and_include_deleted(read_db):
    proj_alias = aliased(RsProj, proj.join(child, proj.c.child_id == child.c.id))
    stmt = select(proj_alias.id).order_by(proj_alias.id).execution_options(include_deleted=True)
    with all_tenants():
        assert (await read_db.execute(stmt)).scalars().all() == [1, 4]


@pytest.mark.parametrize("form", ["bare", "subquery", "cte"])
async def test_text_under_a_scoped_entity_is_refused(read_db, form):
    textual = _child_text()
    sel = {"bare": textual, "subquery": textual.subquery(), "cte": textual.cte()}[form]
    child_alias = aliased(RsChild, sel)
    with tenant_context("a"), pytest.raises(TenantIsolationError, match="SQL text"):
        await read_db.execute(select(child_alias.id))


async def test_text_under_a_scoped_entity_runs_under_all_tenants(read_db):
    child_alias = aliased(RsChild, _child_text().subquery())
    stmt = select(child_alias.id).execution_options(include_deleted=True)
    with all_tenants():
        assert sorted((await read_db.execute(stmt)).scalars()) == [1, 2, 3, 4]


async def test_text_under_an_unscoped_entity_runs(read_db):
    textual = text("SELECT id, child_id FROM read_scope_proj").columns(proj.c.id, proj.c.child_id)
    proj_alias = aliased(RsProj, textual.subquery())
    with tenant_context("a"):
        assert sorted((await read_db.execute(select(proj_alias.id))).scalars()) == [1, 4]


class _InheritBase(DeclarativeBase):
    pass


class _Animal(_InheritBase):
    __tablename__ = "aliased_join_animal"
    id = mapped_column(Integer, primary_key=True)
    kind = mapped_column(String)
    __mapper_args__ = {"polymorphic_on": kind, "polymorphic_identity": "animal"}  # noqa: RUF012


class _Dog(_Animal):
    __tablename__ = "aliased_join_dog"
    id = mapped_column(ForeignKey("aliased_join_animal.id"), primary_key=True)
    __mapper_args__ = {"polymorphic_identity": "dog"}  # noqa: RUF012


@pytest.mark.parametrize(
    "make", [lambda: aliased(_Dog, flat=True), lambda: with_polymorphic(_Animal, [_Dog], flat=True)]
)
def test_orm_built_flat_join_of_an_inheriting_entity_is_its_own(make):
    # The ORM aliases each table of a joined-inheritance mapper once: still the entity's rows.
    insp = inspect(make())
    names = {"aliased_join_animal", "aliased_join_dog"}
    assert isinstance(insp.selectable, Join)
    assert _own_join_only(insp, insp.selectable, names)


def test_subquery_over_an_inheriting_entitys_own_tables_is_its_own():
    # Both tables are _Dog's (its mapper's base and local table): not another table.
    animal, dog = _Animal.__table__, _Dog.__table__
    sub = select(animal.c.id, animal.c.kind).where(animal.c.id == dog.c.id).subquery()
    insp = inspect(aliased(_Dog, sub))
    names = {"aliased_join_animal", "aliased_join_dog"}
    assert _own_rows_only(insp, insp.selectable, names)
    other = animal.alias("other")
    second = select(animal.c.id, animal.c.kind).where(animal.c.id == other.c.id).subquery()
    insp = inspect(aliased(_Dog, second))
    assert not _own_rows_only(insp, insp.selectable, names)
