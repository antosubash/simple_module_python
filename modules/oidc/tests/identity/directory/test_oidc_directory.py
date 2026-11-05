"""The OIDC cache supplies provider-neutral account lookup (#192)."""

import uuid
from datetime import UTC, datetime, timedelta

from oidc.models import OidcUserCache
from simple_module_core.user_directory import get_user_directory


async def _cached(db, email, **kw):
    row = OidcUserCache(issuer="https://idp", subject=uuid.uuid4().hex, email=email, **kw)
    db.add(row)
    await db.flush()
    return row


async def test_registered_directory_looks_up_uuid_spellings_and_unknown_roles(oidc_app):
    directory = get_user_directory(oidc_app)
    assert directory.entity_type is None
    async with oidc_app.state.sm.db.session_factory() as db:
        row = await _cached(db, "alice@example.com", full_name="Alice")
        spellings = [str(row.id), str(row.id).upper(), row.id.hex]
        found = await directory.get_many(
            db, [*spellings, "svc:1", str(uuid.uuid4())], with_roles=True
        )
        assert set(found) == set(spellings)
        for key, user in found.items():
            assert user.id == key
            assert user.label == "Alice"
            assert user.email == "alice@example.com"
            assert user.is_active
            assert user.roles is None
            assert user.email_verified is None
        assert await directory.get_many(db, []) == {}


async def test_directory_search_and_text_ids(oidc_app):
    directory = get_user_directory(oidc_app)
    async with oidc_app.state.sm.db.session_factory() as db:
        first = await _cached(db, "a@example.com", full_name="Okafor A")
        second = await _cached(db, "b-okafor@example.com")
        await _cached(db, "nobody@example.com")
        found = await directory.search(db, " OKAFOR ", limit=10)
        assert [user.id for user in found] == [str(first.id), str(second.id)]
        assert len(await directory.search(db, None, limit=1)) == 1
        assert len(await directory.search(db, "  ", limit=10)) == 3
        assert await directory.search(db, "%", limit=10) == []
        assert await directory.search(db, "_", limit=10) == []
        ids = (await db.execute(directory.match_ids("okafor"))).scalars().all()
        assert set(ids) == {str(first.id), str(second.id)}
        assert (await db.execute(directory.match_ids("%"))).scalars().all() == []


async def test_directory_stats_measure_login_not_account_creation(oidc_app):
    directory = get_user_directory(oidc_app)
    async with oidc_app.state.sm.db.session_factory() as db:
        await _cached(db, "now@example.com", last_login_at=datetime.now(UTC))
        await _cached(db, "old@example.com", last_login_at=datetime.now(UTC) - timedelta(days=60))
        await _cached(db, "unknown@example.com")
        stats = await directory.stats(db, active_window=timedelta(days=7))
        assert stats.total == 3
        assert stats.active_since == 1
        assert stats.created_this_month is None


def test_module_installs_directory_during_registration():
    from types import SimpleNamespace

    from fastapi import FastAPI
    from oidc.module import OidcModule
    from simple_module_core.user_directory import NullUserDirectory

    app = FastAPI()
    app.state.auth = SimpleNamespace()
    OidcModule().register_settings(app)
    assert not isinstance(get_user_directory(app), NullUserDirectory)
