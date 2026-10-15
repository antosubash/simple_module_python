"""Resolving a bearer token: what is accepted, what is refused, and what it costs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from _api_tokens_support import FLAGS_URL, create_pat, load_token, update_token
from api_tokens.constants import TokenKind
from api_tokens.tokens import generate
from starlette.requests import Request


async def test_valid_pat_reads_but_cannot_write(actor, bearer):
    """The acceptance case: scope ``feature_flags.view`` can GET, cannot PUT."""
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]

    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200
    put = await bearer("PUT", f"{FLAGS_URL}anything", token, json={"enabled": True})
    assert put.status_code == 403


async def test_revoke_takes_effect_on_the_next_request(actor, bearer):
    async with actor(admin=True) as a:
        created = await create_pat(a.client, ["feature_flags.view"])
        token, token_id = created["token"], created["item"]["id"]
        assert (await bearer("GET", FLAGS_URL, token)).status_code == 200

        resp = await a.client.post(
            f"/api/api_tokens/tokens/{token_id}/revoke", headers={"X-CSRF-Token": "csrf-test-token"}
        )
        assert resp.status_code == 200
        assert resp.json()["revoked_at"] is not None

    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def test_expired_token_is_refused(app, actor, bearer):
    async with actor(admin=True) as a:
        created = await create_pat(a.client, ["feature_flags.view"])
    await update_token(
        app, created["item"]["id"], expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    assert (await bearer("GET", FLAGS_URL, created["token"])).status_code == 401


async def test_unknown_and_malformed_tokens_are_refused(bearer):
    unknown = generate(TokenKind.PERSONAL).plaintext
    assert (await bearer("GET", FLAGS_URL, unknown)).status_code == 401
    assert (await bearer("GET", FLAGS_URL, "smpat_short")).status_code == 401
    assert (
        await bearer("GET", FLAGS_URL, generate(TokenKind.SERVICE).plaintext)
    ).status_code == 401


async def _set_owner(app, user_id: str, **values) -> None:
    from sqlalchemy import update
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(**values))
        await session.commit()


async def test_inactive_owner_is_refused(app, actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
        await _set_owner(app, a.user_id, is_active=False)
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def test_disabled_owner_is_refused(app, actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
        await _set_owner(app, a.user_id, disabled_at=datetime.now(UTC))
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def test_token_survives_a_fresh_resolver_state(app, actor):
    """Nothing is cached in-process: a restart only needs the database row."""
    from api_tokens.resolver import resolve_api_token

    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "app": app,
    }
    ctx = await resolve_api_token(Request(scope))
    assert ctx is not None
    assert (ctx.auth_kind, ctx.scopes, ctx.id) == ("pat", ["feature_flags.view"], a.user_id)


async def test_last_used_is_written_at_most_once_per_window(app, actor, bearer):
    async with actor(admin=True) as a:
        created = await create_pat(a.client, ["feature_flags.view"])
    token, token_id = created["token"], created["item"]["id"]
    assert (await load_token(app, token_id)).last_used_at is None

    await bearer("GET", FLAGS_URL, token)
    first = (await load_token(app, token_id)).last_used_at
    assert first is not None

    await bearer("GET", FLAGS_URL, token)
    assert (await load_token(app, token_id)).last_used_at == first

    stale = datetime.now(UTC) - timedelta(minutes=10)
    await update_token(app, token_id, last_used_at=stale)
    await bearer("GET", FLAGS_URL, token)
    assert (await load_token(app, token_id)).last_used_at > stale


async def test_users_provider_does_not_look_up_api_tokens(monkeypatch):
    """The provider steps aside for ``smpat_``/``smsk_`` without touching its store."""
    import users.token_strategy
    from users.provider import UsersAuthProvider

    calls: list[str] = []

    async def spy(scope, token):
        calls.append(token)
        return

    monkeypatch.setattr(users.token_strategy, "resolve_bearer", spy)
    provider = UsersAuthProvider()
    for credential in (
        generate(TokenKind.PERSONAL).plaintext,
        generate(TokenKind.SERVICE).plaintext,
    ):
        scope = {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {credential}".encode())],
        }
        assert await provider.resolve_user(Request(scope)) is None
    assert calls == []

    other = {"type": "http", "headers": [(b"authorization", b"Bearer opaque-session-token")]}
    await provider.resolve_user(Request(other))
    assert calls == ["opaque-session-token"]
