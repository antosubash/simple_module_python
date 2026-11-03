"""Rotating refresh tokens are spent once across concurrent cookie requests (#738)."""

import asyncio
import copy
import time

import pytest


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


async def test_waiter_with_expired_outcome_leaves_the_cookie_untouched(renewal, monkeypatch):
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
    # The waiter leaves its cookie alone (no stale Set-Cookie over the winner's).
    assert second.session == r.session


async def test_waiter_timeout_leaves_the_cookie_untouched(renewal, monkeypatch):
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
    assert req.session == r.session


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
        name, expiry = row.outcome_key, row.expires_at
    monkeypatch.setattr(time, "time", lambda: expiry)
    # An expired outcome is ignored on lookup (a read never takes a write lock)
    # and purged by the next publish.
    assert await renewal_outcomes._load(r.app, name) is None
    await renewal_outcomes._publish(r.app, "another-session", "another-lock", {})
    async with independent_session(r.app) as db:
        ids = (await db.execute(select(RefreshOutcome.outcome_key))).scalars().all()
        assert ids == ["another-session"]


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


async def test_publish_failure_keeps_the_renewed_principal(renewal, monkeypatch):
    from auth.oidc_common import renewal_outcomes

    async def locked(*_):
        raise RuntimeError("database is locked")

    r = renewal
    monkeypatch.setattr(renewal_outcomes, "_publish", locked)
    req = r.make_request()
    principal = await r.renew(req)
    assert principal is not None and principal.roles == ["new"]
    assert r.calls == ["old"]
    assert r.tokens.open_refresh_token(r.app, req.session[r.keys.refresh]) == "rotated"
    assert "retry" not in req.session
