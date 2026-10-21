"""``KeycloakDirectory``: users who have signed in, over the cache (GH #501)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from audit_log.models import AuditEntry
from audit_log.resolve import actor_filter, actor_link, resolve_actors
from keycloak.directory import KeycloakDirectory
from keycloak.models import KeycloakUserCache
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_D = KeycloakDirectory()


async def _cached(db: AsyncSession, email: str, **kw) -> KeycloakUserCache:
    row = KeycloakUserCache(keycloak_sub=f"sub-{uuid.uuid4().hex}", email=email, **kw)
    db.add(row)
    await db.flush()
    return row


class TestGetMany:
    async def test_names_a_cached_user(self, db_session: AsyncSession):
        row = await _cached(db_session, "kc@example.com", full_name="Kay Cee")
        found = await _D.get_many(db_session, [str(row.id), "svc:1", str(uuid.uuid4())])
        assert list(found) == [str(row.id)]
        user = found[str(row.id)]
        assert user.label == "Kay Cee"
        assert user.is_active

    async def test_every_spelling_of_one_id_gets_an_entry(self, db_session: AsyncSession):
        row = await _cached(db_session, "two@example.com")
        spellings = [str(row.id), str(row.id).upper(), row.id.hex]
        found = await _D.get_many(db_session, spellings)
        assert sorted(found) == sorted(spellings)
        assert {u.email for u in found.values()} == {"two@example.com"}

    async def test_roles_are_unknown_even_when_asked(self, db_session: AsyncSession):
        """Roles live in the IdP; an empty tuple would claim the user holds none."""
        row = await _cached(db_session, "roles@example.com")
        found = await _D.get_many(db_session, [str(row.id)], with_roles=True)
        assert found[str(row.id)].roles is None


class TestSearchAndMatch:
    async def test_search(self, db_session: AsyncSession):
        await _cached(db_session, "b-okafor@example.com")
        await _cached(db_session, "a@example.com", full_name="Okafor A")
        await _cached(db_session, "nobody@example.com")
        found = await _D.search(db_session, "okafor", limit=10)
        assert [u.email for u in found] == ["a@example.com", "b-okafor@example.com"]

    async def test_match_ids_renders_hyphenated_ids_on_sqlite(self, db_session: AsyncSession):
        """``Uuid`` is 32 bare hex characters on SQLite; the audit trail stores
        ``str(uuid)``. Without the hyphenating expression nothing would match."""
        row = await _cached(db_session, "hyphen@example.com", full_name="Hyphen")
        ids = (await db_session.execute(_D.match_ids("hyphen"))).scalars().all()
        assert ids == [str(row.id)]


class TestStats:
    async def test_counts_signed_in_users_and_cannot_date_creation(self, db_session: AsyncSession):
        await _cached(db_session, "now@example.com", last_login_at=datetime.now(UTC))
        await _cached(
            db_session, "old@example.com", last_login_at=datetime.now(UTC) - timedelta(days=60)
        )
        stats = await _D.stats(db_session, active_window=timedelta(days=7))
        assert stats.total == 2
        assert stats.active_since == 1
        assert stats.created_this_month is None


class TestAuditLogUnderKeycloak:
    """The audit log names and finds Keycloak actors — it used to query the
    empty ``users_user`` table on a Keycloak install."""

    async def test_actor_names_and_search(self, db_session: AsyncSession):
        row = await _cached(db_session, "auditor@example.com", full_name="Audrey")
        db_session.add(
            AuditEntry(
                entity_type="Setting",
                entity_id="k",
                action="updated",
                changes=[],
                user_id=str(row.id),
            )
        )
        db_session.add(
            AuditEntry(
                entity_type="Setting",
                entity_id="k",
                action="updated",
                changes=[],
                user_id=str(uuid.uuid4()),
            )
        )
        await db_session.flush()

        assert await resolve_actors(_D, db_session, [str(row.id)]) == {str(row.id): "Audrey"}
        matched = (
            (await db_session.execute(select(AuditEntry.user_id).where(actor_filter(_D, "audr"))))
            .scalars()
            .all()
        )
        assert matched == [str(row.id)]

    def test_actor_cells_are_unlinked(self):
        registry = AuditLinkRegistry()
        registry.register(AuditLink(entity_type="User", url_template="/admin/users/{id}"))
        assert actor_link(registry, _D, "anything") is None
