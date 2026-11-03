"""Rotating refresh tokens are spent once across concurrent cookie requests (#738)."""

import asyncio
import copy
import time
from types import SimpleNamespace

import pytest
from auth.contracts.schemas import UserContext
from auth.oidc_common.renewal import refresh_session
from auth.oidc_common.session import SessionKeys
from simple_module_core.leases import configure_leases, reset_lease_backend
from simple_module_db.leases import DbLeaseBackend
from starlette.requests import Request


@pytest.fixture(params=["oidc", "keycloak"])
async def renewal(request, tmp_path):
    from importlib import import_module

    from auth.models import Base
    from simple_module_db.leases import LeaseRow
    from simple_module_db.session import init_db

    db_state = init_db(f"sqlite+aiosqlite:///{tmp_path}/refresh.db")
    async with db_state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(LeaseRow.metadata.create_all)

    tokens = import_module(f"{request.param}.tokens")
    keys = SessionKeys("user_ctx", f"{request.param}_refresh_token", "retry", "attempted")
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(
                db=db_state,
                settings=SimpleNamespace(secret_key="test-secret"),
            )
        )
    )
    configure_leases(DbLeaseBackend(db_state.engine))
    session = {
        "user_ctx": UserContext(
            id="user", email="old@example.com", name="Old", roles=["old"]
        ).to_session_dict(),
        keys.refresh: tokens.seal_refresh_token(app, "old"),
        "expires_at": int(time.time()) - 1,
        "oidc_session_id": "opaque-session",
        "gate": "preserved",
    }
    calls = []

    async def refresh(token):
        calls.append(token)
        await asyncio.sleep(refresh.delay)
        if refresh.error is not None:
            raise refresh.error
        return {"refresh_token": "rotated"}

    refresh.delay = 0.1
    refresh.error = None

    async def validate(_):
        return {"sub": "user", "exp": int(time.time()) + 300}

    async def matches(*_):
        return True

    def make_request(cookie=None):
        return Request(
            {
                "type": "http",
                "app": app,
                "session": copy.deepcopy(
                    session if cookie is None else cookie,
                ),
            }
        )

    async def renew(req):
        return await refresh_session(
            req,
            keys=keys,
            cache=object(),
            open_token=tokens.open_refresh_token,
            store_token=tokens.store_refresh_token,
            refresh=refresh,
            validate=validate,
            matches_identity=matches,
            to_context=lambda claims, cache_id: UserContext(
                id=cache_id, email="new@example.com", name="New", roles=["new"]
            ),
        )

    yield SimpleNamespace(**locals())
    reset_lease_backend()
    await db_state.engine.dispose()


@pytest.mark.parametrize("legacy", [False, True])
async def test_parallel_requests_reuse_one_rotated_token(renewal, legacy):
    r = renewal
    if legacy:
        r.session.pop("oidc_session_id")
    first, second = r.make_request(), r.make_request()
    principals = await asyncio.gather(r.renew(first), r.renew(second))
    assert r.calls == ["old"]
    assert all(p is not None and p.roles == ["new"] for p in principals)
    assert first.session == second.session
    assert r.tokens.open_refresh_token(r.app, second.session[r.keys.refresh]) == "rotated"
    assert second.session["gate"] == "preserved"
    assert second.session["oidc_session_id"]


async def test_legacy_session_gets_an_id(renewal):
    r = renewal
    r.session.pop("oidc_session_id")
    req = r.make_request()
    assert await r.renew(req) is not None
    assert len(req.session["oidc_session_id"]) >= 32


async def test_waiter_with_expired_outcome_keeps_cookie_for_retry(renewal, monkeypatch):
    from auth.oidc_common import renewal_outcomes

    r = renewal
    load = renewal_outcomes._load
    reads = 0
    now = int(time.time())

    async def expire_before_waiter_reads(*args):
        nonlocal reads
        reads += 1
        if reads == 2:
            monkeypatch.setattr(time, "time", lambda: now + 31)
        return await load(*args)

    monkeypatch.setattr(renewal_outcomes, "_load", expire_before_waiter_reads)
    first, second = r.make_request(), r.make_request()
    principals = await asyncio.gather(r.renew(first), r.renew(second))
    assert principals[0] is not None
    assert principals[1] is None
    assert r.calls == ["old"]
    assert second.session[r.keys.refresh] == r.session[r.keys.refresh]
    assert second.session["retry"] == now + 61


async def test_waiter_timeout_keeps_cookie_for_retry(renewal, monkeypatch):
    import hashlib

    from auth.oidc_common import renewal_outcomes
    from simple_module_core.leases import lease

    r = renewal
    name = hashlib.sha256(f"{r.keys.refresh}:opaque-session".encode()).hexdigest()
    monkeypatch.setattr(renewal_outcomes, "_WAIT_SECONDS", 0.01)
    req = r.make_request()
    async with lease(f"auth-refresh:{name}", ttl=15):
        assert await r.renew(req) is None
    assert not r.calls
    assert req.session[r.keys.refresh] == r.session[r.keys.refresh]
    assert req.session["retry"] >= int(time.time()) + 29


async def test_outcome_contains_only_sealed_authority_and_is_purged(renewal, monkeypatch):
    from auth.models import RefreshOutcome
    from auth.oidc_common import renewal_outcomes
    from simple_module_db import independent_session
    from sqlmodel import select

    r = renewal
    req = r.make_request()
    assert await r.renew(req) is not None
    async with independent_session(r.app) as db:
        row = (await db.execute(select(RefreshOutcome))).scalar_one()
        assert r.tokens.open_refresh_token(r.app, row.session[r.keys.refresh]) == "rotated"
        assert "rotated" not in str(row.session)
        assert "gate" not in row.session
        name, expiry = row.session_id, row.expires_at
    monkeypatch.setattr(time, "time", lambda: expiry)
    assert await renewal_outcomes._load(r.app, name) is None
    async with independent_session(r.app) as db:
        assert (await db.execute(select(RefreshOutcome))).scalar_one_or_none() is None


async def test_slow_grant_is_cancelled_before_lease_expires(renewal, monkeypatch):
    from auth.oidc_common import renewal_outcomes

    r = renewal
    r.refresh.delay = 1
    monkeypatch.setattr(renewal_outcomes, "_WORK_SECONDS", 0.5)
    req = r.make_request()
    assert await r.renew(req) is None
    assert r.calls == ["old"]
    assert req.session[r.keys.refresh] == r.session[r.keys.refresh]
    assert req.session["retry"] >= int(time.time()) + 29


@pytest.mark.parametrize("status", [400, 503])
async def test_parallel_requests_share_rejection_or_backoff(renewal, status):
    import httpx

    r = renewal
    response = httpx.Response(status, request=httpx.Request("POST", "https://idp/token"))
    r.refresh.error = httpx.HTTPStatusError("refused", request=response.request, response=response)
    first, second = r.make_request(), r.make_request()
    assert await asyncio.gather(r.renew(first), r.renew(second)) == [None, None]
    assert r.calls == ["old"]
    assert first.session == second.session
    if status == 400:
        assert first.session == {"gate": "preserved"}
    else:
        assert first.session[r.keys.refresh] == r.session[r.keys.refresh]
        assert first.session["retry"] >= int(time.time()) + 29


async def test_unavailable_store_does_not_spend_token_or_clear_cookie(renewal, monkeypatch):
    from auth.oidc_common import renewal_outcomes

    async def unavailable(*_):
        raise RuntimeError("unavailable")

    r = renewal
    monkeypatch.setattr(renewal_outcomes, "_load", unavailable)
    req = r.make_request()
    assert await r.renew(req) is None
    assert not r.calls
    assert req.session[r.keys.refresh] == r.session[r.keys.refresh]
    assert req.session["retry"] >= int(time.time()) + 29


async def test_independent_sessions_refresh_without_database_lock_conflicts(renewal):
    r = renewal
    first, second = r.make_request(), r.make_request()
    second.session["oidc_session_id"] = "another-session"
    principals = await asyncio.gather(r.renew(first), r.renew(second))
    assert all(p is not None for p in principals)
    assert r.calls == ["old", "old"]
    assert first.session["oidc_session_id"] == "opaque-session"
    assert second.session["oidc_session_id"] == "another-session"


async def test_older_cookie_copy_cannot_adopt_the_outcome(renewal):
    # Same session id, but an earlier refresh token: it must spend its own
    # (rotated-away) credential at the IdP rather than pick up the new tokens.
    r = renewal
    assert await r.renew(r.make_request()) is not None
    older = copy.deepcopy(r.session)
    older[r.keys.refresh] = r.tokens.seal_refresh_token(r.app, "ancient")
    await r.renew(r.make_request(older))
    assert r.calls == ["old", "ancient"]
