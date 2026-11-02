"""Admin account changes strand cached browser sessions on every worker."""

import pytest
from _users_app_builders import user_row
from simple_module_core.invalidation import InvalidationBus
from users.session_revocation import subscribe
from users.session_version_cache import (
    clear_session_version_cache,
    read_session_version,
    store_session_version,
)


class RecordingTransport:
    def __init__(self):
        self.messages = []

    async def publish(self, message):
        self.messages.append(message)


@pytest.fixture(autouse=True)
def empty_cache():
    clear_session_version_cache()
    yield
    clear_session_version_cache()


@pytest.mark.parametrize("action", ["disable", "enable", "roles"])
async def test_admin_change_revokes_cached_session(
    users_app, anon_client, admin_client, alice, action
):
    promotion = await admin_client.put(
        f"/api/users/admin/{alice.id}/roles", json={"role_names": ["admin"]}
    )
    assert promotion.status_code == 200
    login = await anon_client.post(
        "/api/users/auth/login",
        data={"username": alice.email, "password": "UserPass1!"},
    )
    assert login.status_code == 204
    user = await user_row(users_app, alice.email)
    assert (await anon_client.get("/api/users/admin")).status_code == 200
    assert (await anon_client.get("/api/users/admin")).status_code == 200
    assert read_session_version(user.id) == (True, user.session_version)

    tokens = await anon_client.post(
        "/api/users/auth/token", json={"email": alice.email, "password": "UserPass1!"}
    )
    assert tokens.status_code == 200
    bearer = {"Authorization": f"Bearer {tokens.json()['access_token']}"}
    stale_cookie = anon_client.cookies.get("session")
    transport = RecordingTransport()
    users_app.state.sm.invalidation.set_transport(transport)
    path = f"/api/users/admin/{user.id}"
    if action == "roles":
        response = await admin_client.put(f"{path}/roles", json={"role_names": ["user"]})
    else:
        response = await admin_client.patch(f"{path}/{action}")
    assert response.status_code == 200, response.text
    updated = await user_row(users_app, user.email)
    assert updated.session_version == user.session_version + 1
    assert read_session_version(user.id) == (False, None)
    assert (await anon_client.get("/api/users/admin")).status_code == 401

    assert (await admin_client.get("/api/users/admin", headers=bearer)).status_code == 401

    # Simulate a remote worker with its own stale counter and bus.
    anon_client.cookies.clear()
    anon_client.cookies.set("session", stale_cookie)
    remote = InvalidationBus()
    subscribe(remote)
    store_session_version(user.id, user.session_version)
    assert transport.messages
    for message in transport.messages:
        await remote.deliver(message)
    assert read_session_version(user.id) == (False, None)
    assert (await anon_client.get("/api/users/admin")).status_code == 401
    if action == "roles":
        login = await anon_client.post(
            "/api/users/auth/login",
            data={"username": alice.email, "password": "UserPass1!"},
        )
        assert login.status_code == 204
        assert (await anon_client.get("/api/users/admin")).status_code == 403


async def test_rollback_does_not_publish_revocation(users_app, alice):
    from unittest.mock import Mock

    from users.admin.service import UserService

    transport = RecordingTransport()
    users_app.state.sm.invalidation.set_transport(transport)
    store_session_version(alice.id, alice.session_version)
    async with users_app.state.sm.db.session_factory() as session:
        service = UserService(session, Mock(), users_app)
        changed = await service.disable(alice.id)
        assert changed.session_version == alice.session_version + 1
        assert read_session_version(alice.id) == (True, alice.session_version)
        assert transport.messages == []
        await session.rollback()
    unchanged = await user_row(users_app, alice.email)
    assert unchanged.is_active
    assert unchanged.session_version == alice.session_version
    assert transport.messages == []
