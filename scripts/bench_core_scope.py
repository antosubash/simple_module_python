"""Micro-benchmark for ``core_scope.scope_core`` (GH #559). Not a test.

    uv run python scripts/bench_core_scope.py

Times the per-statement tenancy scope walk on representative ORM selects
(the hot path: every ORM query pays it while tenancy names are set) and a
few Core statements (which are cloned and rewritten). Statements are built
once, as ``filter_statements`` sees them, and ``scope_core`` is called the
way ``query_filter`` calls it, with tenant ``A`` bound.

No ``from __future__ import annotations``: SQLModel resolves the
relationship annotations at class creation.
"""

import sys
import timeit
from collections.abc import Callable
from typing import Any

from simple_module_db.base import create_module_base
from simple_module_db.core_scope import scope_core
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.query_filter import _orm_covered, _scoped_names, _subquery_predicates
from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased, configure_mappers, selectinload
from sqlmodel import Field, Relationship

_Base = create_module_base("bench559")


class Author(_Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "bench559_author"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=100)
    posts: list["Post"] = Relationship(back_populates="author")


class Post(_Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "bench559_post"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(default="", max_length=100)
    author_id: int | None = Field(default=None, foreign_key="bench559_author.id")
    author: Author | None = Relationship(back_populates="posts")


post, author = Post.__table__, Author.__table__


def _orm_statements() -> dict[str, Any]:
    page = select(Post).where(Post.title.like("a%")).order_by(Post.id)
    return {
        "orm get": select(Post).where(Post.id == 1),
        "orm join + selectinload": select(Post)
        .join(Post.author)
        .where(Author.name == "x")
        .options(selectinload(Post.author)),
        "orm subquery in WHERE": select(Post).where(
            Post.author_id.in_(select(Author.id).where(Author.name == "x"))
        ),
        "orm exists in WHERE": select(Author).where(
            exists().where(Post.author_id == Author.id, Post.title == "t")
        ),
        "orm pagination page": page.limit(20).offset(40),
        "orm pagination count": select(func.count()).select_from(page.subquery()),
        "orm aliased join": select(Post).join(aliased(Author), Post.author),
    }


def _core_statements() -> dict[str, Any]:
    return {
        "core select": select(post.c.id).where(post.c.title == "t"),
        "core join": select(post.c.id).select_from(
            post.outerjoin(author, author.c.id == post.c.author_id)
        ),
        "core in ORM WHERE": select(Post).where(Post.author_id.in_(select(author.c.id))),
    }


def _bench(label: str, stmt: Any, call: Callable[[Any], Any], number: int) -> float:
    best = min(timeit.repeat(lambda: call(stmt), number=number, repeat=5))
    micros = best / number * 1e6
    print(f"  {label:<28} {micros:8.2f} µs")
    return micros


def main(number: int = 2000) -> None:
    from simple_module_db.tenancy import current_tenant_id

    configure_mappers()  # fills model_registry's scoped table names
    current_tenant_id.set("A")
    preds = _subquery_predicates(False, False, "A", False)
    names = _scoped_names(False, False)
    covered = _orm_covered(False, False, "A")

    def call(stmt: Any) -> Any:
        return scope_core(stmt, preds, names, covered)

    for title, stmts in (("ORM", _orm_statements()), ("Core", _core_statements())):
        print(f"{title} statements (best of 5 x {number}):")
        times = [_bench(label, stmt, call, number) for label, stmt in stmts.items()]
        print(f"  {'mean':<28} {sum(times) / len(times):8.2f} µs")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
