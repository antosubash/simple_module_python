"""One resolver call per entity type per page, never one per row.

A 50-row page of user edits must not become 50 round trips, and a resolver
that raises must not take the rest of the page's names — or a streaming
export — down with it.
"""

from __future__ import annotations

from audit_log.models import AuditEntry
from audit_log.resolve import resolve_entity_labels
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


class TestBatching:
    """One call per entity type per page, never one per row: a 50-row page of
    user edits must not become 50 round trips."""

    async def test_resolver_is_called_once_with_every_id(self, db_session: AsyncSession) -> None:
        calls: list[list[str]] = []

        async def resolve(_db, ids: list[str]) -> dict[str, str]:
            calls.append(sorted(ids))
            return {i: f"name-{i}" for i in ids}

        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(
                entity_type="User",
                url_template="/u/{id}",
                table_name="users_user",
                label_resolver=resolve,
            )
        )

        labels = await resolve_entity_labels(
            db_session, registry, [("User", "a"), ("User", "b"), ("User", "a")]
        )

        assert calls == [["a", "b"]]
        assert labels == {("User", "a"): "name-a", ("User", "b"): "name-b"}

    async def test_types_without_a_resolver_are_skipped(self, db_session: AsyncSession) -> None:
        registry = AuditLinkRegistry()
        registry.register(AuditLink(entity_type="StoredFile", url_template="/f/{id}"))

        assert await resolve_entity_labels(db_session, registry, [("StoredFile", "z")]) == {}

    async def test_a_failing_resolver_does_not_take_down_the_page(
        self, db_session: AsyncSession
    ) -> None:
        """A module's naming query is not load-bearing for the audit record."""

        async def boom(_db, _ids):
            raise RuntimeError("no")

        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(entity_type="User", url_template="/u/{id}", label_resolver=boom)
        )

        assert await resolve_entity_labels(db_session, registry, [("User", "a")]) == {}

    async def test_a_database_error_leaves_the_session_usable(
        self, db_session: AsyncSession
    ) -> None:
        """A resolver that fails *in the database* aborts the transaction on
        Postgres, and every later query answers "current transaction is
        aborted" — which would take the rest of the page's names with it and
        truncate a streaming export mid-file. The session has to be reset."""
        rollbacks = []
        original = db_session.rollback

        async def spy() -> None:
            rollbacks.append(True)
            await original()

        async def db_boom(_db, _ids):
            raise DBAPIError("SELECT 1", {}, Exception("column does not exist"))

        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(entity_type="Setting", url_template="/s/{id}", label_resolver=db_boom)
        )
        db_session.rollback = spy  # type: ignore[method-assign]
        try:
            labels = await resolve_entity_labels(db_session, registry, [("Setting", "1")])
        finally:
            db_session.rollback = original  # type: ignore[method-assign]

        assert labels == {}
        assert rollbacks == [True]
        # The session still answers — the export's next batch depends on it.
        assert (await db_session.execute(select(AuditEntry))).all() is not None

    async def test_one_failing_module_does_not_cost_the_others_their_names(
        self, db_session: AsyncSession
    ) -> None:
        async def boom(_db, _ids):
            raise DBAPIError("SELECT 1", {}, Exception("nope"))

        async def fine(_db, ids):
            return {i: f"name-{i}" for i in ids}

        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(entity_type="Setting", url_template="/s/{id}", label_resolver=boom)
        )
        registry.register(
            AuditLink(entity_type="User", url_template="/u/{id}", label_resolver=fine)
        )

        labels = await resolve_entity_labels(
            db_session, registry, [("Setting", "1"), ("User", "a")]
        )

        assert labels == {("User", "a"): "name-a"}
