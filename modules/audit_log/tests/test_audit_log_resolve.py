"""Resolving the raw ids an audit entry stores into names and links.

The browse screen showed `user_id` as a bare uuid and left `entity_id`
unlinked, so an entry told you something changed but not who or where.
"""

from __future__ import annotations

import uuid

from audit_log.resolve import actor_link, entity_link, resolve_actors
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User


def _registry() -> AuditLinkRegistry:
    reg = AuditLinkRegistry()
    reg.register(
        AuditLink(entity_type="users_user", url_template="/users/admin/{id}", label="User")
    )
    return reg


class TestEntityLink:
    def test_registered_table_resolves_to_a_url(self):
        ref = entity_link(_registry(), "users_user", "a91")
        assert ref == {"url": "/users/admin/a91", "label": "User"}

    def test_unclaimed_table_renders_unlinked(self):
        """Join rows and blob stores have no screen — the id still shows."""
        ref = entity_link(_registry(), "permissions_user_permission", "x1")
        assert ref["url"] is None
        assert ref["label"] == "permissions_user_permission"

    def test_missing_label_falls_back_to_the_table_name(self):
        reg = AuditLinkRegistry()
        reg.register(AuditLink(entity_type="files_file", url_template="/f/{id}"))
        assert entity_link(reg, "files_file", "z")["label"] == "files_file"


class TestActorLink:
    def test_uses_the_registered_users_route(self):
        """Hardcoding /users/admin/{id} here would 404 the moment the users
        module moved its prefix, and duplicate what the registry owns."""
        assert actor_link(_registry(), "a91") == "/users/admin/a91"

    def test_none_when_no_module_claims_users(self):
        """The audit log still renders without the users module installed."""
        assert actor_link(AuditLinkRegistry(), "a91") is None


class TestResolveActors:
    async def test_resolves_full_name_when_present(self, db_session: AsyncSession):
        user = User(
            email="sam@example.com",
            hashed_password="x",
            full_name="Sam Carter",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        resolved = await resolve_actors(db_session, [str(user.id)])
        assert resolved[str(user.id)] == "Sam Carter"

    async def test_falls_back_to_email_without_a_name(self, db_session: AsyncSession):
        user = User(email="noname@example.com", hashed_password="x", is_active=True)
        db_session.add(user)
        await db_session.flush()

        resolved = await resolve_actors(db_session, [str(user.id)])
        assert resolved[str(user.id)] == "noname@example.com"

    async def test_unknown_ids_are_simply_absent(self, db_session: AsyncSession):
        """A deleted account must not blank the row — the caller shows the id."""
        missing = str(uuid.uuid4())
        assert await resolve_actors(db_session, [missing]) == {}

    async def test_empty_and_none_ids_short_circuit(self, db_session: AsyncSession):
        assert await resolve_actors(db_session, [None, None]) == {}
        assert await resolve_actors(db_session, []) == {}

    async def test_unparseable_ids_do_not_fail_the_page(self, db_session: AsyncSession):
        """System actors from another id space must not 500 the audit log."""
        assert await resolve_actors(db_session, ["celery-worker-1"]) == {}

    async def test_batches_the_whole_page_in_one_pass(self, db_session: AsyncSession):
        users = [
            User(email=f"u{i}@example.com", hashed_password="x", full_name=f"U{i}", is_active=True)
            for i in range(3)
        ]
        db_session.add_all(users)
        await db_session.flush()

        ids = [str(u.id) for u in users]
        # Repeats are normal: one admin usually authors most of a page.
        resolved = await resolve_actors(db_session, ids + ids)
        assert set(resolved) == set(ids)
