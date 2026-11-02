"""The revocation cache's rough edges: a racy read, and an early invalidation.

The 30-second cache in front of ``User.session_version`` is a deliberate trade
(``session_version_cache``), but two things around it were not.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_db import RequestSession
from sqlalchemy import select
from users.models import User
from users.session_version_cache import (
    SESSION_VERSION_TTL_SECONDS,
    clear_session_version_cache,
    configure_session_version_cache,
    read_session_version,
    session_version_ttl,
    store_session_version,
)

_CREDS = {"username": "admin@example.com", "password": "AdminPass1!"}


@pytest.fixture(autouse=True)
def _cold_cache():
    clear_session_version_cache()
    yield
    configure_session_version_cache(SESSION_VERSION_TTL_SECONDS)
    clear_session_version_cache()


class TestTheReadIsNotRacy:
    """``if k in cache: return cache[k]`` on a TTLCache can raise between the
    two — the entry expires in the gap. The caller has no ``except KeyError``,
    so landing in that window turned a revocation check into a 500."""

    def test_a_miss_reports_no_hit(self):
        assert read_session_version("nobody") == (False, None)

    def test_a_cached_none_is_a_hit(self):
        """``None`` means "no such row" and is a legitimate cached answer;
        collapsing it with "not cached" costs a DB read on every request."""
        store_session_version("gone", None)
        assert read_session_version("gone") == (True, None)

    def test_a_cached_value_is_a_hit(self):
        store_session_version("dana", 4)
        assert read_session_version("dana") == (True, 4)

    def test_an_entry_expiring_mid_read_does_not_raise(self, monkeypatch):
        """The race, made deterministic: the membership test succeeds and the
        subscript then finds nothing. One `.get` cannot be torn this way."""

        class _Vanishing(dict):
            """A cache whose entry expires between the test and the subscript."""

            ttl = SESSION_VERSION_TTL_SECONDS  # so the fixture can restore afterwards

            def __contains__(self, key):
                return True

            def get(self, key, default=None):
                return default

            def __getitem__(self, key):
                raise KeyError(key)

        monkeypatch.setattr(
            "users.session_version_cache._SESSION_VERSIONS", _Vanishing(), raising=True
        )
        assert read_session_version("dana") == (False, None)


class TestTheWindowIsAnOperatorChoice:
    def test_the_default_is_the_documented_thirty_seconds(self):
        assert session_version_ttl() == SESSION_VERSION_TTL_SECONDS

    def test_it_can_be_shortened(self):
        configure_session_version_cache(5)
        assert session_version_ttl() == 5

    def test_zero_disables_caching(self):
        """The honest knob for a deployment that will not accept any window in
        which one worker has not seen another's revocation."""
        configure_session_version_cache(0)
        store_session_version("dana", 4)
        assert read_session_version("dana") == (False, None)

    def test_reconfiguring_to_the_same_window_keeps_the_warm_cache(self):
        store_session_version("dana", 4)
        configure_session_version_cache(int(session_version_ttl()))
        assert read_session_version("dana") == (True, 4)

    def test_a_negative_window_is_floored_rather_than_rejected(self):
        configure_session_version_cache(-1)
        assert session_version_ttl() == 0


class TestInvalidationWaitsForTheCommit:
    """Clearing before the row is durable means a failed commit leaves the cache
    empty and the counter unchanged — the next read repopulates the *old* value
    and quietly re-admits everything the bump was meant to strand."""

    @staticmethod
    async def _admin_id(app):
        async with app.state.sm.db.session_factory() as session:
            return (
                await session.execute(select(User.id).where(User.email == "admin@example.com"))
            ).scalar_one()

    @pytest.mark.anyio
    async def test_a_password_change_clears_the_entry(self, users_app, anon_client):
        assert (await anon_client.post("/api/users/auth/login", data=_CREDS)).status_code == 204
        user_id = await self._admin_id(users_app)
        store_session_version(user_id, 0)
        assert read_session_version(user_id)[0] is True

        resp = await anon_client.post(
            "/api/users/me/password",
            json={"current_password": "AdminPass1!", "new_password": "NewAdminPass1!"},
        )
        assert resp.status_code == 204, resp.text
        assert read_session_version(user_id)[0] is False

    @pytest.mark.anyio
    async def test_revoke_all_clears_the_entry(self, users_app, anon_client):
        assert (await anon_client.post("/api/users/auth/login", data=_CREDS)).status_code == 204
        user_id = await self._admin_id(users_app)
        store_session_version(user_id, 0)
        assert read_session_version(user_id)[0] is True

        resp = await anon_client.post("/api/users/me/sessions/revoke-all")
        assert resp.status_code == 204, resp.text
        assert read_session_version(user_id)[0] is False

    @pytest.mark.anyio
    async def test_the_cache_still_holds_when_the_commit_begins(self, users_app, anon_client):
        """The handler wiring, not just the hook.

        Fault injection cannot show this: patching ``commit`` to raise trips
        ``user_manager.update``'s own commit first, before either invalidation
        runs. So observe the ordering instead — record whether the entry is
        still cached each time a commit begins. Inline invalidation empties it
        during the handler, so the *last* observation is a miss; hung on the
        commit, the entry is still there when the final commit starts.
        """
        from sqlalchemy import event
        from sqlalchemy.orm import Session

        assert (await anon_client.post("/api/users/auth/login", data=_CREDS)).status_code == 204
        user_id = await self._admin_id(users_app)
        store_session_version(user_id, 0)

        cached_at_commit: list[bool] = []

        def observe(session):
            cached_at_commit.append(read_session_version(user_id)[0])

        event.listen(Session, "before_commit", observe)
        try:
            resp = await anon_client.post(
                "/api/users/me/password",
                json={"current_password": "AdminPass1!", "new_password": "NewAdminPass1!"},
            )
        finally:
            event.remove(Session, "before_commit", observe)

        assert resp.status_code == 204, resp.text
        assert cached_at_commit, "no commit was observed — the probe did not fire"
        assert cached_at_commit[-1] is True, (
            "the cache was cleared before the row was durable: a failed commit would "
            "leave the old counter to be read back as current"
        )
        # And it is gone once the commit has landed.
        assert read_session_version(user_id)[0] is False

    @pytest.mark.anyio
    async def test_a_rolled_back_bump_leaves_the_cache_intact(self, users_app):
        """The whole point of the move: no commit, no invalidation. Otherwise
        the cache is emptied for a bump that never happened, and the next read
        caches the old counter as if it were current."""
        user_id = await self._admin_id(users_app)
        store_session_version(user_id, 3)

        from users.session_version_cache import forget_session_version

        async with users_app.state.sm.db.session_factory() as session:
            assert isinstance(session, RequestSession)
            session.on_commit(lambda: forget_session_version(user_id))
            await session.rollback()

        assert read_session_version(user_id) == (True, 3)


class TestTheProviderStillSeesRevocations:
    @pytest.mark.anyio
    async def test_a_bump_signs_the_other_browser_out(self, users_app, anon_client):
        """End to end, through the cache: the guarantee the hardening must not
        have broken."""
        from simple_module_test import forge_session_cookie

        assert (await anon_client.post("/api/users/auth/login", data=_CREDS)).status_code == 204
        user_id = await self._admin_id_of(users_app)

        cookie = forge_session_cookie(
            str(users_app.state.sm.settings.secret_key),
            {"user_id": str(user_id), "session_version": 0},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=users_app),
            base_url="http://testserver",
            cookies={"session": cookie},
        ) as other:
            assert (await other.get("/admin/users/")).status_code == 200

            assert (await anon_client.post("/api/users/me/sessions/revoke-all")).status_code == 204
            assert (await other.get("/admin/users/")).status_code in (401, 302, 303)

    @staticmethod
    async def _admin_id_of(app):
        async with app.state.sm.db.session_factory() as session:
            return (
                await session.execute(select(User.id).where(User.email == "admin@example.com"))
            ).scalar_one()


def test_the_module_level_cache_is_the_one_the_helpers_use():
    """Guards the rebuild in ``configure_session_version_cache``: the helpers
    look the global up by name, so reassigning it has to reach them.

    Read through the module rather than the name imported at collection time —
    that name still points at the cache the rebuild replaced, which is exactly
    the trap this test exists to describe.
    """
    import users.session_version_cache as cache_module

    configure_session_version_cache(7)
    store_session_version("dana", 1)
    assert cache_module._SESSION_VERSIONS.get("dana") == 1
    assert cache_module._SESSION_VERSIONS.ttl == 7
