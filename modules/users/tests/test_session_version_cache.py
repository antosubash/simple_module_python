"""The revocation check does not pay for a DB round-trip on every request.

``_version_still_current`` runs on the cached-context path, which is *most*
requests — every page load, every asset-adjacent view. One indexed primary-key
read is cheap, but it is not free, and it was unconditional.

The trade is stated where it lives: a revocation performed in another worker
takes up to the TTL to be seen here. The process that performed it drops its
own entry immediately, so the browser that pressed the button never sees the
stale answer.
"""

from __future__ import annotations

import uuid

import pytest
from users import provider as provider_module
from users.provider import forget_session_version


@pytest.fixture(autouse=True)
def _empty_cache():
    provider_module.clear_session_version_cache()
    yield
    provider_module.clear_session_version_cache()


class _CountingFactory:
    """Wraps the real session factory and counts how often it is opened."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._inner(*args, **kwargs)


@pytest.fixture
def counted(users_app):
    db = users_app.state.sm.db
    original = db.session_factory
    factory = _CountingFactory(original)
    db.session_factory = factory
    yield factory
    db.session_factory = original


async def _user_id(users_app) -> uuid.UUID:
    from sqlalchemy import select
    from users.models import User

    async with users_app.state.sm.db.session_factory() as session:
        return (
            await session.execute(select(User.id).where(User.email == "admin@example.com"))
        ).scalar_one()


def _scope(users_app) -> dict:
    return {"app": users_app}


class TestTheCacheSkipsTheQuery:
    @pytest.mark.anyio
    async def test_the_first_check_reads_the_row(self, users_app, counted):
        provider = provider_module.UsersAuthProvider()
        user_id = await _user_id(users_app)
        counted.calls = 0

        assert await provider._version_still_current(_scope(users_app), user_id, {}) is True
        assert counted.calls == 1

    @pytest.mark.anyio
    async def test_the_second_check_does_not(self, users_app, counted):
        provider = provider_module.UsersAuthProvider()
        user_id = await _user_id(users_app)
        await provider._version_still_current(_scope(users_app), user_id, {})
        counted.calls = 0

        assert await provider._version_still_current(_scope(users_app), user_id, {}) is True
        assert counted.calls == 0

    @pytest.mark.anyio
    async def test_a_cached_version_still_compares_against_the_session_stamp(
        self, users_app, counted
    ):
        """A hit must not mean "yes" — it means "the stored value is N"."""
        provider = provider_module.UsersAuthProvider()
        user_id = await _user_id(users_app)
        await provider._version_still_current(_scope(users_app), user_id, {})
        counted.calls = 0

        stale = {"session_version": 99}
        assert await provider._version_still_current(_scope(users_app), user_id, stale) is False
        assert counted.calls == 0


class TestInvalidation:
    @pytest.mark.anyio
    async def test_forgetting_makes_the_next_check_query_again(self, users_app, counted):
        provider = provider_module.UsersAuthProvider()
        user_id = await _user_id(users_app)
        await provider._version_still_current(_scope(users_app), user_id, {})
        counted.calls = 0

        forget_session_version(user_id)

        assert await provider._version_still_current(_scope(users_app), user_id, {}) is True
        assert counted.calls == 1

    @pytest.mark.anyio
    async def test_forgetting_an_unknown_id_is_a_no_op(self):
        forget_session_version(uuid.uuid4())


class TestTheEndpointsInvalidate:
    """The process that revoked must not serve its own stale entry."""

    @pytest.mark.anyio
    async def test_revoke_all_drops_the_entry(self, users_app, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!"},
        )
        assert resp.status_code == 204, resp.text
        user_id = await _user_id(users_app)
        provider = provider_module.UsersAuthProvider()
        await provider._version_still_current(_scope(users_app), user_id, {})

        assert (await anon_client.post("/api/users/me/sessions/revoke-all")).status_code == 204

        assert provider_module.peek_session_version(user_id) is None

    @pytest.mark.anyio
    async def test_a_password_change_drops_the_entry(self, users_app, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!"},
        )
        assert resp.status_code == 204, resp.text
        user_id = await _user_id(users_app)
        provider = provider_module.UsersAuthProvider()
        await provider._version_still_current(_scope(users_app), user_id, {})

        changed = await anon_client.post(
            "/api/users/me/password",
            json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
        )
        assert changed.status_code == 204, changed.text

        assert provider_module.peek_session_version(user_id) is None
