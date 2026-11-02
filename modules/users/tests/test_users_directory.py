"""``UsersDirectory``: the users module's answer to the core directory (GH #501)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from simple_module_core.user_directory import GET_MANY_CHUNK, get_user_directory
from sqlalchemy.ext.asyncio import AsyncSession
from users.directory import UsersDirectory
from users.models import Role, User, UserRole

_D = UsersDirectory()


async def _user(db: AsyncSession, email: str, **kw) -> User:
    user = User(email=email, hashed_password="x", is_active=True, **kw)
    db.add(user)
    await db.flush()
    return user


class TestGetMany:
    async def test_keys_by_the_callers_spelling(self, db_session: AsyncSession):
        user = await _user(db_session, "ada@example.com", full_name="Ada")
        upper = str(user.id).upper()
        found = await _D.get_many(db_session, [upper])
        assert list(found) == [upper]
        assert found[upper].label == "Ada"
        assert found[upper].id == upper

    async def test_every_spelling_of_one_id_gets_an_entry(self, db_session: AsyncSession):
        """Two spellings of one id must not collapse: each caller key is labelled."""
        user = await _user(db_session, "twice@example.com", full_name="Twice")
        spellings = [str(user.id), str(user.id).upper()]
        found = await _D.get_many(db_session, spellings, with_roles=True)
        assert sorted(found) == sorted(spellings)
        assert [found[k].label for k in spellings] == ["Twice", "Twice"]

    async def test_unknown_and_foreign_ids_are_absent(self, db_session: AsyncSession):
        found = await _D.get_many(db_session, [str(uuid.uuid4()), "celery-worker-1", ""])
        assert found == {}

    async def test_roles_only_when_asked(self, db_session: AsyncSession):
        user = await _user(db_session, "roles@example.com")
        role = Role(name=f"editor-{uuid.uuid4().hex[:6]}")
        db_session.add(role)
        await db_session.flush()
        db_session.add(UserRole(user_id=user.id, role_id=role.id))
        await db_session.flush()

        plain = await _D.get_many(db_session, [str(user.id)])
        assert plain[str(user.id)].roles is None
        with_roles = await _D.get_many(db_session, [str(user.id)], with_roles=True)
        assert with_roles[str(user.id)].roles == (role.name,)

    async def test_a_user_without_roles_holds_none_rather_than_unknown(
        self, db_session: AsyncSession
    ):
        user = await _user(db_session, "bare@example.com")
        found = await _D.get_many(db_session, [str(user.id)], with_roles=True)
        assert found[str(user.id)].roles == ()

    async def test_disabled_or_inactive_is_not_active(self, db_session: AsyncSession):
        disabled = await _user(db_session, "off@example.com", disabled_at=datetime.now(UTC))
        inactive = await _user(db_session, "inactive@example.com")
        inactive.is_active = False
        await db_session.flush()
        found = await _D.get_many(db_session, [str(disabled.id), str(inactive.id)])
        assert not found[str(disabled.id)].is_active
        assert not found[str(inactive.id)].is_active

    async def test_more_ids_than_one_chunk(self, db_session: AsyncSession):
        user = await _user(db_session, "chunk@example.com")
        ids = [str(uuid.uuid4()) for _ in range(GET_MANY_CHUNK + 10)] + [str(user.id)]
        found = await _D.get_many(db_session, ids)
        assert list(found) == [str(user.id)]


class TestSearchAndMatch:
    async def test_search_by_name_or_email(self, db_session: AsyncSession):
        await _user(db_session, "zed@example.com", full_name="Grace Okafor")
        await _user(db_session, "okafor.b@example.com")
        await _user(db_session, "other@example.com")
        found = await _D.search(db_session, "okafor", limit=10)
        assert [u.email for u in found] == ["okafor.b@example.com", "zed@example.com"]

    async def test_empty_term_lists_everyone_up_to_the_limit(self, db_session: AsyncSession):
        for n in range(3):
            await _user(db_session, f"all{n}@example.com")
        assert len(await _D.search(db_session, None, limit=2)) == 2
        assert len(await _D.search(db_session, "  ", limit=10)) >= 3

    async def test_match_ids_selects_the_text_form_audit_rows_store(self, db_session: AsyncSession):
        user = await _user(db_session, "match@example.com", full_name="Matchable")
        ids = (await db_session.execute(_D.match_ids("matchab"))).scalars().all()
        assert ids == [str(user.id)]

    async def test_like_metacharacters_are_literal(self, db_session: AsyncSession):
        await _user(db_session, "dana_x@example.com")
        await _user(db_session, "danaYx@example.com")
        found = await _D.search(db_session, "dana_x", limit=10)
        assert [u.email for u in found] == ["dana_x@example.com"]


class TestStats:
    async def test_counts(self, db_session: AsyncSession):
        before = await _D.stats(db_session, active_window=timedelta(days=7))
        await _user(db_session, "recent@example.com", last_login_at=datetime.now(UTC))
        await _user(
            db_session,
            "stale@example.com",
            last_login_at=datetime.now(UTC) - timedelta(days=30),
        )
        after = await _D.stats(db_session, active_window=timedelta(days=7))
        assert after.total == (before.total or 0) + 2
        assert after.active_since == (before.active_since or 0) + 1
        assert after.created_this_month == (before.created_this_month or 0) + 2


class TestRegistration:
    async def test_users_module_installs_its_directory(self, app):
        assert isinstance(get_user_directory(app), UsersDirectory)

    async def test_audit_label_resolver_delegates(self, db_session: AsyncSession):
        from users.audit import resolve_user_labels

        user = await _user(db_session, "label@example.com")
        assert await resolve_user_labels(db_session, [str(user.id)]) == {
            str(user.id): "label@example.com"
        }
