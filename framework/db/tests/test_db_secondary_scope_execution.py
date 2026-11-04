"""The ``secondary`` criteria read a scope recorded per execution, on every engine.

``_secondary_scope`` listens on the ``Engine`` class: an engine with no policy
bound still records each execution's scope (and its options), and the scope is
cleared once the execution is done. An UPDATE / DELETE skips the link table's
soft-delete criterion, like the main filter skips soft-delete on writes.
"""

import asyncio

from _db_read_scope_models import Base, RsChild, RsParent, child, link, parent, read_db
from simple_module_db import _secondary_scope
from simple_module_db.tenancy import tenant_context
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.pool import StaticPool

__all__ = ["read_db"]


async def test_update_through_secondary_ignores_trashed_link_rows_like_the_filter(read_db):
    # Child 2 is linked by link 3 (tenant a, trashed) and link 2 (tenant b).
    stmt = update(RsParent).where(RsParent.linked.any(RsChild.id == 2)).values(id=RsParent.id)
    with tenant_context("a"):
        assert (await read_db.execute(stmt)).rowcount == 1
    with tenant_context("c"):
        assert (await read_db.execute(stmt)).rowcount == 0  # tenant criteria still apply
    probe = select(RsParent.id).where(RsParent.linked.any(RsChild.id == 2))
    with tenant_context("a"):
        assert (await read_db.execute(probe)).all() == []  # a read keeps soft-delete


async def test_scope_is_cleared_after_each_execution(read_db):
    with tenant_context("a"):
        await read_db.execute(select(RsParent.id).join(RsParent.linked))
        assert _secondary_scope._scope.get() is None

        async def child_task():
            return _secondary_scope._scope.get()

        assert await asyncio.create_task(child_task()) is None


def _unbound_engine():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(parent), [{"id": 1, "tenant_id": "a"}])
        conn.execute(
            insert(child),
            [
                {"id": 1, "parent_id": 1, "tenant_id": "a", "is_deleted": False},
                {"id": 2, "parent_id": 1, "tenant_id": "a", "is_deleted": False},
                {"id": 4, "parent_id": 1, "tenant_id": "b", "is_deleted": False},
            ],
        )
        conn.execute(
            insert(link),
            [
                {"id": 1, "parent_id": 1, "child_id": 1, "tenant_id": "a", "is_deleted": False},
                {"id": 2, "parent_id": 1, "child_id": 2, "tenant_id": "b", "is_deleted": False},
                {"id": 3, "parent_id": 1, "child_id": 2, "tenant_id": "a", "is_deleted": True},
            ],
        )
    return engine


def test_engine_without_a_policy_applies_only_the_secondary_conditions():
    """On a plain ``Connection`` no loader criteria apply; the link conditions do."""
    engine = _unbound_engine()
    linked = select(RsChild.id).join(RsParent.linked).order_by(RsChild.id)
    kids = select(RsChild.id).join(RsParent.kids).order_by(RsChild.id)
    try:
        with engine.connect() as conn, tenant_context("a"):
            assert conn.execute(linked).scalars().all() == [1]
            options = {"all_tenants": True, "include_deleted": True}
            everything = conn.execute(linked.execution_options(**options)).scalars().all()
            assert everything == [1, 2, 2]
            # The children themselves are not filtered: tenant b's child 4 is read.
            assert conn.execute(kids).scalars().all() == [1, 2, 4]
    finally:
        engine.dispose()
