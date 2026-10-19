"""Core joins over ``Model.__table__`` are tenant / soft-delete scoped (#506).

An outer join's nullable side must be filtered without turning the join
inner: ``unused`` (no links in tenant A) must survive, and tenant B's three
links to ``used`` must never be counted.
"""

from __future__ import annotations

import pytest
from _core_scope_models import link, make_strict, plain, seeded, soft, tag
from simple_module_db.tenancy import TenantIsolationError
from sqlalchemy import func, select

__all__ = ["seeded"]


async def _rows(session, stmt, **options):
    if options:
        stmt = stmt.execution_options(**options)
    return sorted((await session.execute(stmt)).all(), key=repr)


def _link_counts(right=None, *, on=None):
    right = link if right is None else right
    on = right.c.tag_id == tag.c.id if on is None else on
    return (
        select(tag.c.name, func.count(right.c.id))
        .select_from(tag.outerjoin(right, on))
        .group_by(tag.c.name)
    )


async def test_left_join_count_star_keeps_parent_and_isolates(seeded):
    stmt = (
        select(tag.c.name, func.count())
        .select_from(tag.outerjoin(link, link.c.tag_id == tag.c.id))
        .group_by(tag.c.name)
    )
    assert dict(await _rows(seeded, stmt)) == {"used": 1, "unused": 1}


async def test_left_join_column_count(seeded):
    assert dict(await _rows(seeded, _link_counts())) == {"used": 1, "unused": 0}


async def test_left_join_selected_child_column_stays_outer(seeded):
    stmt = select(tag.c.name, link.c.article_id).select_from(
        tag.outerjoin(link, link.c.tag_id == tag.c.id)
    )
    assert await _rows(seeded, stmt) == [("unused", None), ("used", 1)]


async def test_aliased_right_table(seeded):
    alias = link.alias("l2")
    assert dict(await _rows(seeded, _link_counts(alias))) == {"used": 1, "unused": 0}


async def test_soft_deleted_right_row(seeded):
    on = soft.c.tag_id == tag.c.id
    assert dict(await _rows(seeded, _link_counts(soft, on=on))) == {"used": 1, "unused": 0}


async def test_include_deleted_is_honoured(seeded):
    stmt = _link_counts(soft, on=soft.c.tag_id == tag.c.id)
    assert dict(await _rows(seeded, stmt, include_deleted=True)) == {"used": 2, "unused": 0}


async def test_all_tenants_is_honoured(seeded):
    rows = dict(await _rows(seeded, _link_counts(), all_tenants=True))
    assert rows == {"used": 4, "unused": 0, "b-tag": 0}


async def test_inner_join(seeded):
    stmt = (
        select(tag.c.name, func.count())
        .select_from(tag.join(link, link.c.tag_id == tag.c.id))
        .group_by(tag.c.name)
    )
    assert dict(await _rows(seeded, stmt)) == {"used": 1}


async def test_full_join_both_sides_scoped(seeded):
    stmt = select(tag.c.name, link.c.article_id).select_from(
        tag.outerjoin(link, link.c.tag_id == tag.c.id, full=True)
    )
    assert await _rows(seeded, stmt) == [("unused", None), ("used", 1)]


async def test_full_join_unscoped_left(seeded):
    stmt = select(plain.c.name, link.c.article_id).select_from(
        plain.outerjoin(link, link.c.tag_id == plain.c.id, full=True)
    )
    assert await _rows(seeded, stmt) == [("p1", 1), ("p3", None)]


async def test_join_chain(seeded):
    stmt = select(tag.c.name, link.c.article_id, soft.c.id).select_from(
        tag.outerjoin(link, link.c.tag_id == tag.c.id).outerjoin(soft, soft.c.tag_id == tag.c.id)
    )
    assert await _rows(seeded, stmt) == [("unused", None, None), ("used", 1, 1)]


async def test_nested_join_as_nullable_side(seeded):
    inner = link.join(soft, soft.c.tag_id == link.c.tag_id)
    stmt = select(tag.c.name, link.c.article_id, soft.c.id).select_from(
        tag.outerjoin(inner, link.c.tag_id == tag.c.id)
    )
    assert await _rows(seeded, stmt) == [("unused", None, None), ("used", 1, 1)]


async def test_select_outerjoin_method_on_core_table(seeded):
    """``select(...).outerjoin(link, ...)`` records a setup join, not a ``Join``."""
    stmt = (
        select(tag.c.name, func.count())
        .select_from(tag)
        .outerjoin(link, link.c.tag_id == tag.c.id)
        .group_by(tag.c.name)
    )
    assert dict(await _rows(seeded, stmt)) == {"used": 1, "unused": 1}


async def test_select_full_outerjoin_method_on_core_table(seeded):
    stmt = select(plain.c.name, link.c.article_id).outerjoin_from(
        plain, link, link.c.tag_id == plain.c.id, full=True
    )
    assert await _rows(seeded, stmt) == [("p1", 1), ("p3", None)]


@pytest.mark.parametrize("full", [False, True])
async def test_strict_without_tenant_refuses_a_core_join(seeded, full):
    make_strict(seeded)
    stmt = select(plain.c.name, link.c.article_id).select_from(
        plain.outerjoin(link, link.c.tag_id == plain.c.id, full=full)
    )
    with pytest.raises(TenantIsolationError):
        await seeded.execute(stmt)
