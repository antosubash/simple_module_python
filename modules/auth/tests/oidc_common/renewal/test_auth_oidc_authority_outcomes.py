"""Renewal waiters must reject outcomes minted by a different authority."""

import pytest


@pytest.mark.parametrize("marker", [None, "another-authority"])
async def test_waiter_rejects_missing_or_changed_authority(renewal, marker):
    r = renewal
    r.session["oidc_authority"] = "current-authority"
    assert await r.renew(r.make_request()) is not None
    waiter = r.make_request()
    waiter.session["oidc_authority"] = marker
    assert await r.renew(waiter) is None
    assert waiter.session == {}
    assert r.calls == ["old"]


async def test_waiter_keeps_matching_authority(renewal):
    r = renewal
    r.session["oidc_authority"] = "current-authority"
    first, second = r.make_request(), r.make_request()
    assert await r.renew(first) is not None
    assert await r.renew(second) is not None
    assert second.session["oidc_authority"] == "current-authority"
    assert r.calls == ["old"]


async def test_renewal_publishes_authority(renewal):
    from auth.models import RefreshOutcome
    from simple_module_db import independent_session
    from sqlmodel import select

    r = renewal
    r.session["oidc_authority"] = "current-authority"
    req = r.make_request()
    assert await r.renew(req) is not None
    assert req.session["oidc_authority"] == "current-authority"
    async with independent_session(r.app) as db:
        row = (await db.execute(select(RefreshOutcome))).scalar_one()
        assert row.session["oidc_authority"] == "current-authority"


async def test_waiter_adopts_an_unmarked_outcome_from_before_the_upgrade(renewal):
    r = renewal
    assert await r.renew(r.make_request()) is not None  # published without a marker
    waiter = r.make_request()
    waiter.session["oidc_authority"] = "current-authority"
    assert await r.renew(waiter) is not None
    assert r.calls == ["old"]
