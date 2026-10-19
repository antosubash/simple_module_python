"""Core references hidden inside an otherwise-ORM SELECT are still scoped (#559).

``scope_core``'s walk skips ORM-annotated elements and never expands most of
an ORM select's FROMs, so these pin that a plain ``Model.__table__`` column
or subquery anywhere in an ORM statement — its columns, ``WHERE``,
``HAVING``, ``ORDER BY`` or a join — keeps reaching the filters. Tenant A
sees one link (id 1, on tag ``used``); tenant B's links 7, 8 and 9 also
point at ``used`` and must never be counted.
"""

from __future__ import annotations

import pytest
from _core_scope_models import Link, Plain, Tag, _rows, link, make_strict, seeded, tag
from simple_module_db.tenancy import TenantIsolationError
from sqlalchemy import func, or_, select

__all__ = ["seeded"]


def _links_of_tag():
    """Correlated: tenant A's links on the outer ``Tag`` row."""
    return select(func.count()).where(link.c.tag_id == Tag.id).scalar_subquery()


def _b_article_links():
    """Uncorrelated: links on B's article 7 — none for tenant A."""
    return select(func.count()).select_from(link).where(link.c.article_id == 7).scalar_subquery()


SHAPES = {
    "core column": (
        lambda: select(Tag.name, link.c.id).where(link.c.tag_id == Tag.id),
        [("used", 1)],
    ),
    "core column, entity first": (
        lambda: select(Tag, link.c.article_id).where(link.c.tag_id == Tag.id),
        "one",
    ),
    "scalar subquery column": (
        lambda: select(Tag.name, _links_of_tag()),
        [("unused", 0), ("used", 1)],
    ),
    # Not leaks: the entity's own table through a Core column, and a Core
    # column on an outer-joined entity, whose ON already holds its criteria
    # (a WHERE predicate there would turn the LEFT join inner, #417).
    "entity's own table in WHERE": (
        lambda: select(Tag.name).where(tag.c.id == Tag.id, tag.c.name == "used"),
        [("used",)],
    ),
    "core column on outer-joined entity": (
        lambda: (
            select(Tag.name, Link.id)
            .outerjoin(Link, Link.tag_id == Tag.id)
            .where(or_(link.c.id.is_(None), link.c.article_id == 1))
        ),
        [("unused", None), ("used", 1)],
    ),
    "core IN subquery in WHERE": (
        lambda: select(Tag.name).where(
            Tag.id.in_(select(link.c.tag_id).where(link.c.article_id == 7))
        ),
        [],
    ),
    "core scalar in WHERE": (
        lambda: select(Tag.name).where(_links_of_tag() > 1),
        [],
    ),
    "core scalar in HAVING": (
        lambda: select(Tag.name).group_by(Tag.name).having(_b_article_links() > 0),
        [],
    ),
    "core scalar in ORDER BY": (
        # Tenant A: ``used`` has 1 link, so it sorts first. Counting B's
        # links (4) would leave the alphabetical order.
        lambda: select(Tag.name).order_by((_links_of_tag() == 1).desc(), Tag.name),
        "ordered",
    ),
    "core inner join": (
        lambda: select(Tag.name).join(link, link.c.tag_id == Tag.id),
        [("used",)],
    ),
    "core outer join": (
        lambda: select(Tag.name, link.c.id).outerjoin(link, link.c.tag_id == Tag.id),
        [("unused", None), ("used", 1)],
    ),
    "core subquery join": (
        lambda: select(Tag.name).join(
            (sq := select(link.c.tag_id).subquery()), sq.c.tag_id == Tag.id
        ),
        [("used",)],
    ),
    "core exists in ORM join ON": (
        lambda: select(Tag.name).join(Link, (Link.tag_id == Tag.id) & (_b_article_links() == 0)),
        [("used",)],
    ),
}


@pytest.mark.parametrize("shape", list(SHAPES))
async def test_core_inside_orm_select_is_scoped(seeded, shape):
    build, expected = SHAPES[shape]
    if expected == "ordered":
        names = [r[0] for r in (await seeded.execute(build())).all()]
        assert names == ["used", "unused"]
    elif expected == "one":
        rows = (await seeded.execute(build())).all()
        assert [(r[0].name, r[1]) for r in rows] == [("used", 1)]
    else:
        assert await _rows(seeded, build()) == expected


# ``Plain`` carries no criteria of its own, so the refusal can only come
# from the Core reference to ``link``.
STRICT = {
    "column": lambda: select(Plain.name, link.c.id).where(link.c.tag_id == Plain.id),
    "WHERE subquery": lambda: select(Plain.name).where(Plain.id.in_(select(link.c.tag_id))),
    "HAVING": lambda: select(Plain.name).group_by(Plain.name).having(_b_article_links() > 0),
    "ORDER BY": lambda: select(Plain.name).order_by(
        select(func.count()).where(link.c.tag_id == Plain.id).scalar_subquery()
    ),
    "join": lambda: select(Plain.name).join(link, link.c.tag_id == Plain.id),
}


@pytest.mark.parametrize("shape", list(STRICT))
async def test_core_inside_orm_select_refuses_without_tenant(seeded, shape):
    make_strict(seeded)
    with pytest.raises(TenantIsolationError):
        await seeded.execute(STRICT[shape]())
