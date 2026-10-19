"""Core references below the top level are tenant / soft-delete scoped (#506).

Aliases, subqueries, CTEs, scalar subqueries, compound selects, the extra
FROM of an UPDATE / DELETE, an INSERT ... SELECT source and ``exists()``
over a join or inside an ``ON`` clause. Tenant A sees one link (id 1);
tenant B's links (7, 8, 9) must never surface.
"""

from __future__ import annotations

import pytest
from _core_scope_models import _rows, link, make_strict, plain, seeded, soft, tag
from simple_module_db.tenancy import TenantIsolationError
from simple_module_test.database import database_is_postgres
from sqlalchemy import (
    and_,
    delete,
    except_,
    exists,
    func,
    insert,
    intersect,
    literal,
    select,
    union,
    union_all,
    update,
)

__all__ = ["seeded"]


def _link_ids():
    return select(link.c.id)


SHAPES = {
    "alias": (lambda: select(link.alias("a").c.id), [(1,)]),
    "alias count": (lambda: select(func.count()).select_from(tag.alias("a")), [(2,)]),
    "subquery": (lambda: select(select(link).subquery().c.id), [(1,)]),
    "cte": (lambda: select(select(link).cte("c").c.id), [(1,)]),
    "count of cte": (
        lambda: select(func.count()).select_from(select(soft.c.id).cte("sc")),
        [(1,)],
    ),
    "scalar subquery": (
        lambda: select(select(func.count()).select_from(link).scalar_subquery()),
        [(1,)],
    ),
    "correlated scalar": (
        lambda: select(
            tag.c.name,
            select(func.count()).where(link.c.tag_id == tag.c.id).scalar_subquery(),
        ),
        [("unused", 0), ("used", 1)],
    ),
    "where-only from": (lambda: select(func.count()).where(link.c.tag_id == 1), [(1,)]),
    "union": (lambda: union(_link_ids(), _link_ids()), [(1,)]),
    "union_all": (lambda: union_all(_link_ids(), _link_ids()), [(1,), (1,)]),
    "intersect": (lambda: intersect(_link_ids(), _link_ids()), [(1,)]),
    "except": (lambda: except_(_link_ids(), select(link.c.id).where(link.c.id == 0)), [(1,)]),
    "exists over join": (
        lambda: select(plain.c.name).where(
            exists(
                select(link.c.id)
                .select_from(link.join(tag, tag.c.id == link.c.tag_id))
                .where(link.c.article_id == 7)
            )
        ),
        [],
    ),
    "exists in ON": (
        lambda: select(plain.c.name).select_from(
            plain.join(
                tag,
                and_(
                    tag.c.id == plain.c.id,
                    exists().where(link.c.tag_id == tag.c.id, link.c.article_id == 7),
                ),
            )
        ),
        [],
    ),
    # Codex: not leaks before #506 either — kept as regressions.
    "core inner join": (
        lambda: select(link.c.id).select_from(link.join(tag, tag.c.id == link.c.tag_id)),
        [(1,)],
    ),
    "single-table exists": (
        lambda: select(plain.c.name).where(exists().where(link.c.article_id == 7)),
        [],
    ),
}


@pytest.mark.parametrize("shape", list(SHAPES))
async def test_shape_never_sees_other_tenants(seeded, shape):
    build, expected = SHAPES[shape]
    assert await _rows(seeded, build()) == expected


@pytest.mark.parametrize("shape", ["alias", "subquery", "cte", "union", "exists over join"])
async def test_strict_without_tenant_refuses(seeded, shape):
    make_strict(seeded)
    with pytest.raises(TenantIsolationError):
        await seeded.execute(SHAPES[shape][0]())


async def test_all_tenants_option_reaches_nested_selects(seeded):
    stmt = select(select(link).subquery().c.id).execution_options(all_tenants=True)
    assert len((await seeded.execute(stmt)).all()) == 4


async def test_update_from_another_tenants_row_matches_nothing(seeded):
    stmt = (
        update(plain).where(plain.c.id == tag.c.id, tag.c.name == "b-tag").values(name="hijacked")
    )
    assert (await seeded.execute(stmt)).rowcount == 0


async def test_delete_through_subquery_matches_nothing(seeded):
    stmt = delete(plain).where(plain.c.id.in_(select(tag.c.id).where(tag.c.name == "b-tag")))
    assert (await seeded.execute(stmt)).rowcount == 0


@pytest.mark.skipif(not database_is_postgres(), reason="DELETE ... USING needs Postgres")
async def test_delete_using_another_tenants_row_matches_nothing(seeded):
    stmt = delete(plain).where(plain.c.id == tag.c.id, tag.c.name == "b-tag")
    assert (await seeded.execute(stmt)).rowcount == 0


async def test_insert_from_select_copies_only_own_rows(seeded):
    source = select((link.c.id + 100).label("id"), literal("copy").label("name"))
    await seeded.execute(insert(plain).from_select(["id", "name"], source))
    copied = select(plain.c.id).where(plain.c.id >= 100)
    assert (await seeded.execute(copied)).all() == [(101,)]
