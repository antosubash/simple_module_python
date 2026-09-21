"""What the revocation check does when the database is unreachable.

``_version_still_current`` fails **open** on a read error — it keeps the session —
and that is deliberate: a `False` return does not merely 401 the request, it sends
the caller into ``_forget(session)``, which drops the user id, the cached context,
the version stamp, the expiry *and* the "keep me signed in" choice. Failing closed
during a database blip therefore signs everyone out for real and makes them
re-authenticate, rather than inconveniencing them for the length of the outage.

The trade-off is priced in the other direction too, and it is cheap: exploiting the
open branch needs a replayed revoked cookie *and* a simultaneous database outage,
during which nearly everything the session could be used for needs the same
database.

None of that was pinned by a test before, which is why these exist. The behaviour
is a security decision, so it should not be possible to reverse it silently in
either direction — a future change of mind should show up here as a failure whose
name says what was decided.

The asymmetry the tests draw out: a cache **hit** cannot fail open at all, because
it is an in-memory comparison. Only a **miss** reaches the read. So the cache is an
incidental fail-closed shield, and anything that empties it — a TTL expiry, a cold
process, an invalidation broadcast, or setting the TTL to 0 — widens the window in
which the open branch is reachable.
"""

from __future__ import annotations

import uuid

import pytest
from users.constants import SESSION_VERSION_KEY
from users.provider import UsersAuthProvider
from users.session_version_cache import (
    clear_session_version_cache,
    configure_session_version_cache,
    read_session_version,
    store_session_version,
)

_STAMPED = 3
_REVOKED_TO = 4


@pytest.fixture(autouse=True)
def _cold_cache():
    clear_session_version_cache()
    yield
    clear_session_version_cache()
    configure_session_version_cache(30)


class _BrokenFactory:
    """A session factory standing in for an unreachable database."""

    def __call__(self, *args, **kwargs):
        raise RuntimeError("connection pool exhausted")


class _Sm:
    def __init__(self, factory) -> None:
        self.db = type("_Db", (), {"session_factory": factory})()


class _App:
    def __init__(self, factory) -> None:
        self.state = type("_State", (), {"sm": _Sm(factory)})()


def _scope(factory) -> dict:
    return {"app": _App(factory)}


async def _still_current(factory, session) -> bool:
    return await UsersAuthProvider()._version_still_current(_scope(factory), _USER_ID, session)


_USER_ID = uuid.uuid4()


class TestUnreachableDatabase:
    async def test_a_warm_cache_refuses_a_revoked_session(self):
        """The shield: an in-memory comparison cannot fail open."""
        store_session_version(_USER_ID, _REVOKED_TO)

        allowed = await _still_current(_BrokenFactory(), {SESSION_VERSION_KEY: _STAMPED})

        assert allowed is False

    async def test_a_cold_cache_admits_it(self):
        """The documented fail-open. Reverse this only on purpose."""
        allowed = await _still_current(_BrokenFactory(), {SESSION_VERSION_KEY: _STAMPED})

        assert allowed is True, (
            "the revocation check now fails closed on a database error. That is a "
            "security-relevant change of behaviour, not a bug fix: a False return "
            "sends the caller into _forget(), which destroys the session and discards "
            "'keep me signed in', so every signed-in user must re-authenticate for the "
            "length of any database blip. If that is intended, change this test and say "
            "so in provider._version_still_current."
        )

    async def test_the_outage_is_not_cached(self):
        """The next request must retry rather than inherit the failure."""
        await _still_current(_BrokenFactory(), {SESSION_VERSION_KEY: _STAMPED})

        assert read_session_version(_USER_ID) == (False, None)


class TestReachableDatabaseIsStricter:
    async def test_a_healthy_read_still_refuses_a_revoked_session(self, users_app):
        """The happy path, for contrast: nothing about fail-open loosens this."""
        from users.models import User

        async with users_app.state.sm.db.session_factory() as session:
            user = User(
                email="failopen@example.com",
                hashed_password="x",
                is_active=True,
                session_version=_REVOKED_TO,
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        allowed = await UsersAuthProvider()._version_still_current(
            {"app": users_app}, user_id, {SESSION_VERSION_KEY: _STAMPED}
        )

        assert allowed is False


class TestZeroTtlRemovesTheShield:
    """``ttl=0`` is offered to security-minded operators, and has a second effect.

    It is the strictest setting for cross-worker lag — nothing is cached, so no
    worker can serve a stale counter. It is also the *widest* setting for the
    fail-open branch, because every cached-path request then takes the database
    read instead of a fraction of them. Both halves are true at once, which is why
    the knob's docstring now says so.
    """

    def test_nothing_is_retained_at_all(self):
        configure_session_version_cache(0)
        store_session_version(_USER_ID, _REVOKED_TO)

        assert read_session_version(_USER_ID) == (False, None)

    async def test_so_every_request_reaches_the_fail_open_branch(self):
        configure_session_version_cache(0)
        store_session_version(_USER_ID, _REVOKED_TO)

        allowed = await _still_current(_BrokenFactory(), {SESSION_VERSION_KEY: _STAMPED})

        assert allowed is True, (
            "with ttl=0 the store is a no-op, so the warm-cache shield never applies"
        )
