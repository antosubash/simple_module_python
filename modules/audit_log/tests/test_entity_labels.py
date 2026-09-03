"""Entity cells name the row that changed, not the table it lives in.

An audit row stores a class name and a primary key. Rendering "User a91f3c2b…"
tells a reader which *kind* of thing changed and nothing about *which* one, so
every investigation starts by pasting the id into another screen. The owning
module is the only code that knows a ``Setting`` is named by its key and a
``User`` by ``full_name or email``, so it supplies a batch resolver alongside
its link, and the browse view spends it once per entity type per page.
"""

from __future__ import annotations

import uuid

import httpx
from audit_log.constants import ACTION_UPDATED
from audit_log.models import AuditEntry
from audit_log.resolve import resolve_entity_labels
from background_tasks.models import TaskExecution
from feature_flags.models import FeatureFlagOverride
from settings.models import Setting
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User

VIEW_URL = "/admin/audit-log/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}


async def _browse(client: httpx.AsyncClient, **params: str) -> dict:
    resp = await client.get(VIEW_URL, params=params, headers=INERTIA_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


def _entity(props: dict, entity_id: str) -> dict:
    matches = [i["entity"] for i in props["items"] if i["entity_id"] == entity_id]
    assert matches, f"no audit row for {entity_id!r} in {[i['entity_id'] for i in props['items']]}"
    return matches[0]


async def _seed_entry(app, *, entity_type: str, entity_id: str) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.add(
            AuditEntry(
                entity_type=entity_type,
                entity_id=entity_id,
                action=ACTION_UPDATED,
                changes=[{"field": "x", "old": 1, "new": 2}],
            )
        )
        await session.commit()


class TestUserLabels:
    async def test_a_user_row_is_named_by_full_name(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            user = User(
                email="sam@example.com",
                hashed_password="x",
                full_name="Sam Okafor",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            user_id = str(user.id)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        entity = _entity(await _browse(authenticated_client), user_id)

        assert entity["display"] == "Sam Okafor"
        assert entity["table_name"] == "users_user"

    async def test_a_nameless_user_falls_back_to_the_email(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The deck's fourth row is "rob@example.com" — an invite that has not
        been accepted has no name yet, and the email is what identifies it."""
        async with app.state.sm.db.session_factory() as session:
            user = User(email="rob@example.com", hashed_password="x", is_active=True)
            session.add(user)
            await session.commit()
            user_id = str(user.id)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        assert _entity(await _browse(authenticated_client), user_id)["display"] == "rob@example.com"

    async def test_a_deleted_row_falls_back_to_the_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The record outlives the row it describes; the id is still the truth."""
        gone = str(uuid.uuid4())
        await _seed_entry(app, entity_type="User", entity_id=gone)

        assert _entity(await _browse(authenticated_client), gone)["display"] == gone


class TestOtherModuleLabels:
    async def test_a_setting_is_named_by_its_key(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            row = Setting(key="users.smtp_host", value="mail.example.com")
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="Setting", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "users.smtp_host"
        assert entity["table_name"] == "settings_setting"

    async def test_a_task_execution_is_named_by_its_task(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            row = TaskExecution(
                celery_task_id=str(uuid.uuid4()), task_name="files.generate_thumbnail"
            )
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="TaskExecution", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "files.generate_thumbnail"
        assert entity["table_name"] == "background_tasks_task_execution"

    async def test_a_flag_override_is_named_by_the_flag_not_the_row_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """An override's primary key is a meaningless integer. What the reader
        is looking for is which flag was toggled."""
        async with app.state.sm.db.session_factory() as session:
            row = FeatureFlagOverride(name="beta_dashboard", enabled=True)
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="FeatureFlagOverride", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "beta_dashboard"
        assert entity["table_name"] == "feature_flags_override"

    async def test_an_unclaimed_type_shows_the_class_name_and_the_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Join rows have no owner and no screen — the tag still says something."""
        await _seed_entry(app, entity_type="UserRole", entity_id="7")

        entity = _entity(await _browse(authenticated_client), "7")

        assert entity["display"] == "7"
        assert entity["table_name"] == "UserRole"
        assert entity["url"] is None


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
