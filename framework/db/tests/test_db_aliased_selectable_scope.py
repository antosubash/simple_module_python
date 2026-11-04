"""``aliased(Model, <subquery or CTE>)``: scoped through ORM entities, else refused.

The ORM renders such an entity from the selectable it was built over, so the
filter cannot rewrite what that selectable reads. Built from ORM entities it
is scoped by the loader criteria; reading only the entity's own table it is
scoped on the rows it returns; any other Core read of a scoped table inside
it is refused (``_entity_selectables``).
"""

import pytest
from _db_read_scope_models import RsChild, RsProj, child, lax_read_db, proj, read_db
from simple_module_db.tenancy import TenantIsolationError, all_tenants, tenant_context
from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased

__all__ = ["lax_read_db", "read_db"]


def _proj_over_core_child():
    """Projects whose child is tenant ``b``'s: a Core read inside the selectable."""
    inner = select(child.c.id).where(child.c.tenant_id == "b")
    return aliased(RsProj, select(proj).where(proj.c.child_id.in_(inner)).subquery())


@pytest.mark.parametrize("form", ["subquery", "cte"])
async def test_core_read_inside_aliased_selectable_is_refused(read_db, form):
    sub = select(proj).where(proj.c.child_id.in_(select(child.c.id)))
    proj_alias = aliased(RsProj, sub.subquery() if form == "subquery" else sub.cte())
    with tenant_context("a"), pytest.raises(TenantIsolationError, match="read_scope_child"):
        await read_db.execute(select(proj_alias.id))


async def test_refused_shape_also_refused_on_a_single_tenant_install(lax_read_db):
    # Soft-delete still applies, and the selectable cannot be filtered for it.
    with pytest.raises(TenantIsolationError):
        await lax_read_db.execute(select(_proj_over_core_child().id))


async def test_refused_shape_runs_under_all_tenants_and_include_deleted(read_db):
    stmt = select(_proj_over_core_child().id).execution_options(include_deleted=True)
    with all_tenants():
        assert (await read_db.execute(stmt)).scalars().all() == [4]


async def test_orm_read_inside_aliased_selectable_is_scoped(read_db):
    inner = select(RsChild.id).where(RsChild.tenant_id == "b")
    proj_alias = aliased(RsProj, select(RsProj).where(RsProj.child_id.in_(inner)).subquery())
    with tenant_context("a"):
        assert (await read_db.execute(select(proj_alias.id))).scalars().all() == []
    with tenant_context("b"):
        assert (await read_db.execute(select(proj_alias.id))).scalars().all() == [4]


async def test_own_table_selectable_is_scoped_by_the_entity_criteria(read_db):
    child_alias = aliased(RsChild, select(child).where(child.c.parent_id == 1).subquery())
    with tenant_context("a"):
        assert sorted((await read_db.execute(select(child_alias.id))).scalars()) == [1, 2]
    with tenant_context("b"):
        assert sorted((await read_db.execute(select(child_alias.id))).scalars()) == [4]


async def test_own_table_with_a_nested_core_read_is_refused(read_db):
    probe = exists(select(child.c.id).where(child.c.tenant_id == "b"))
    child_alias = aliased(RsChild, select(child).where(probe).subquery())
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await read_db.execute(select(child_alias.id))


async def test_own_table_joined_to_another_scoped_table_is_refused(read_db):
    other = child.alias("other")
    joined = select(child).join(other, other.c.id == child.c.parent_id)
    child_alias = aliased(RsChild, joined.subquery())
    with tenant_context("a"), pytest.raises(TenantIsolationError):
        await read_db.execute(select(child_alias.id))


async def test_aliased_selectable_via_select_from_is_not_rendered_twice(read_db):
    inner = select(RsChild.id).where(RsChild.parent_id == 1)
    proj_alias = aliased(RsProj, select(RsProj).where(RsProj.child_id.in_(inner)).subquery("p"))
    stmt = (
        select(proj_alias.id)
        .select_from(proj_alias)
        .where(proj_alias.child_id.in_(select(child.c.id)))
    )
    with tenant_context("a"):
        assert (await read_db.execute(stmt)).scalars().all() == [1]


# Each combines rows before the entity's criteria filter the result.
_COMBINING = {
    "group by": lambda: select(child).group_by(child.c.parent_id),
    "having": lambda: select(child).having(func.count(child.c.id) > 0),
    "window": lambda: select(
        child, func.max(child.c.id).over(partition_by=child.c.parent_id).label("top")
    ),
    "aggregate": lambda: select(
        func.max(child.c.id).label("id"), func.min(child.c.tenant_id).label("tenant_id")
    ),
    # Not a known aggregate name: an unknown function is not trusted to be row-wise.
    "unlisted aggregate": lambda: select(
        func.any_value(child.c.id).label("id"), func.any_value(child.c.tenant_id).label("tenant_id")
    ),
}


@pytest.mark.parametrize("shape", list(_COMBINING))
async def test_own_table_selectable_that_combines_rows_is_refused(read_db, shape):
    child_alias = aliased(RsChild, _COMBINING[shape]().subquery())
    with tenant_context("a"), pytest.raises(TenantIsolationError, match="read_scope_child"):
        await read_db.execute(select(child_alias.id))


async def test_row_wise_function_and_nested_unscoped_aggregate_stay_allowed(read_db):
    top_proj = select(func.max(proj.c.child_id)).scalar_subquery()
    row_wise = func.coalesce(func.lower(child.c.tenant_id), "") != "z"
    sub = select(child).where(func.abs(child.c.id) > 0, row_wise, child.c.id <= top_proj)
    child_alias = aliased(RsChild, sub.subquery())
    with tenant_context("a"):
        assert sorted((await read_db.execute(select(child_alias.id))).scalars()) == [1, 2]
    with tenant_context("b"):
        assert sorted((await read_db.execute(select(child_alias.id))).scalars()) == [4]
