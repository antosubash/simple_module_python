"""Logout drops shared outcomes; a slow publish does not undo a renewal (#738)."""

import asyncio
import copy

from sqlmodel import select


async def _outcomes(r):
    from auth.models import RefreshOutcome
    from simple_module_db import independent_session

    async with independent_session(r.app) as db:
        return (await db.execute(select(RefreshOutcome))).scalars().all()


async def test_logout_removes_the_outcome_so_a_replayed_cookie_cannot_adopt_it(renewal):
    from auth.oidc_common.renewal_outcomes import forget_outcomes

    r = renewal
    pre_rotation = copy.deepcopy(r.session)
    assert await r.renew(r.make_request()) is not None
    rows = await _outcomes(r)
    assert len(rows) == 1 and rows[0].lock_key
    await forget_outcomes(r.app, r.keys, r.make_request().session)
    assert await _outcomes(r) == []
    await r.renew(r.make_request(pre_rotation))
    assert r.calls == ["old", "old"]  # nothing to adopt: it spent its own credential


async def test_logout_clears_the_outcome_of_a_session_without_an_id(renewal):
    from auth.oidc_common.renewal_outcomes import forget_outcomes

    r = renewal
    r.session.pop("oidc_session_id")
    assert await r.renew(r.make_request()) is not None
    assert len(await _outcomes(r)) == 1
    await forget_outcomes(r.app, r.keys, copy.deepcopy(r.session))
    assert await _outcomes(r) == []


async def test_logout_from_a_renewed_legacy_cookie_clears_its_outcome(renewal):
    from auth.oidc_common.renewal_outcomes import forget_outcomes

    r = renewal
    r.session.pop("oidc_session_id")
    req = r.make_request()
    assert await r.renew(req) is not None
    assert req.session["oidc_session_id"]  # the renewal gave the cookie an id
    await forget_outcomes(r.app, r.keys, req.session)
    assert await _outcomes(r) == []


async def test_logout_keeps_other_sessions_outcomes(renewal):
    from auth.oidc_common.renewal_outcomes import forget_outcomes

    r = renewal
    other = r.make_request()
    other.session["oidc_session_id"] = "another-session"
    assert await r.renew(other) is not None
    await forget_outcomes(r.app, r.keys, r.make_request().session)
    assert len(await _outcomes(r)) == 1


async def test_forget_failure_never_blocks_logout(renewal, monkeypatch, caplog):
    from auth.oidc_common import renewal_outcomes

    def broken(_):
        raise RuntimeError("secret-sql-parameter")

    r = renewal
    monkeypatch.setattr(renewal_outcomes, "independent_session", broken)
    await renewal_outcomes.forget_outcomes(r.app, r.keys, r.make_request().session)
    assert "RuntimeError" in caplog.text
    assert "secret-sql-parameter" not in caplog.text


async def test_slow_publish_still_returns_the_renewed_principal(renewal, monkeypatch):
    from auth.oidc_common import renewal_outcomes

    async def slow(*_):
        await asyncio.sleep(1)  # intentional-sleep: publish outlasts the work timeout

    r = renewal
    monkeypatch.setattr(renewal_outcomes, "_WORK_SECONDS", 0.5)
    monkeypatch.setattr(renewal_outcomes, "_publish", slow)
    req = r.make_request()
    principal = await r.renew(req)
    assert principal is not None and principal.roles == ["new"]
    assert r.tokens.open_refresh_token(r.app, req.session[r.keys.refresh]) == "rotated"
    assert "retry" not in req.session
