"""The ``users.administrator`` wizard action: anonymous creation of the first admin.

What is pinned here, in the order the action's docstring argues it:

* it completes the step and releases the gate;
* it is gated on *its own step*, so an install that re-enters setup mode with
  administrators intact (schema behind head) refuses it;
* it re-checks under a lock inside the inserting transaction, so concurrent
  requests mint exactly one superuser;
* the password goes through the module's real policy.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from simple_module_test.setup_wizard import post_step, wizard_client, wizard_headers
from sqlalchemy import func, select
from users.models import User
from users.setup import STEP_ADMINISTRATOR
from users.setup_action import create_first_administrator

pytestmark = pytest.mark.anyio

_BEHIND = {
    "current_revision": "abc123",
    "head_revision": "def456",
    "is_current": False,
    "pending_count": 1,
}


async def _superusers(app) -> list[str]:
    async with app.state.sm.db.session_factory() as session:
        rows = await session.scalars(
            select(User.email).where(User.is_superuser.is_(True), User.is_active.is_(True))
        )
        return list(rows)


def _schema_behind(app, monkeypatch) -> None:
    """Put the install back into setup mode the way a deploy-before-migrate does."""
    app.state.migration = dict(_BEHIND)

    # The gate re-reads a behind-head verdict from the database rather than
    # trusting the boot snapshot, so the stub has to keep saying "behind".
    async def _still_behind(*_args, **_kwargs):
        return dict(_BEHIND)

    monkeypatch.setattr(
        "simple_module_hosting.migrations.migration_status", _still_behind, raising=True
    )


async def test_creating_an_admin_completes_setup(setup_pending_app) -> None:
    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(
            client,
            STEP_ADMINISTRATOR,
            {"email": "root@example.com", "password": "SetupPass1!", "full_name": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["result"] == {"created": True, "email": "root@example.com"}

        # The gate must now release for ordinary routes, and the wizard close.
        after = await client.get("/", follow_redirects=False)
        wizard = await client.get("/setup")

    assert after.status_code != 302
    assert wizard.status_code == 404
    assert await _superusers(setup_pending_app) == ["root@example.com"]


async def test_refused_when_setup_mode_reopens_with_admins_intact(app, monkeypatch) -> None:
    """A behind-head schema reopens the wizard, not admin creation.

    ``create_app`` registers ``host.migrations`` for every install, so a live
    deployment that ships code ahead of its migration job re-enters setup mode
    with its administrators intact. Gated on "setup mode" this action would
    hand an anonymous request a fresh superuser there.
    """
    _schema_behind(app, monkeypatch)

    async with wizard_client(app) as client:
        resp = await post_step(
            client, STEP_ADMINISTRATOR, {"email": "intruder@example.com", "password": "Whatever1!"}
        )

    assert resp.status_code == 409
    assert "intruder@example.com" not in await _superusers(app)


async def test_handler_rechecks_inside_its_transaction(app) -> None:
    """The race loser: it passed the wizard's step check, then someone else
    committed an admin. The in-transaction re-check must refuse it."""
    request = SimpleNamespace(app=app)

    with pytest.raises(HTTPException) as exc:
        await create_first_administrator(
            request, {"email": "late@example.com", "password": "LatePass1!"}
        )

    assert exc.value.status_code == 409
    assert "late@example.com" not in await _superusers(app)


async def test_concurrent_submissions_create_one_admin(setup_pending_app) -> None:
    clients = [wizard_client(setup_pending_app) for _ in range(4)]
    try:
        # Every client loads the wizard first, as concurrent operators would —
        # once the winner commits, the wizard is gone for anyone arriving later.
        headers = [await wizard_headers(c) for c in clients]
        responses = await asyncio.gather(
            *(
                c.post(
                    f"/setup/steps/{STEP_ADMINISTRATOR}",
                    json={"email": f"root{n}@example.com", "password": "RacePass1!"},
                    headers=h,
                )
                for n, (c, h) in enumerate(zip(clients, headers, strict=True))
            )
        )
    finally:
        for c in clients:
            await c.aclose()

    codes = sorted(r.status_code for r in responses)
    assert codes.count(200) == 1, codes
    # Losers are refused by the step gate or the in-transaction re-check (409),
    # or — once the winner has closed the wizard entirely — by its absence (404).
    assert all(code in (200, 404, 409) for code in codes), codes
    async with setup_pending_app.state.sm.db.session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.is_superuser.is_(True))
        )
    assert count == 1


async def test_existing_non_admin_address_is_refused(setup_pending_app) -> None:
    """create_admin leaves an existing account untouched; reporting success for
    a step that is still pending would leave the operator stuck."""
    from users.bootstrap import create_standard_user

    async with setup_pending_app.state.sm.db.session_factory() as session:
        await create_standard_user(session, email="user@example.com", password="UserPass1!")

    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(
            client, STEP_ADMINISTRATOR, {"email": "user@example.com", "password": "Another1!"}
        )

    assert resp.status_code == 409
    assert await _superusers(setup_pending_app) == []


@pytest.mark.parametrize(
    "password,why",
    [
        ("        ", "whitespace-only, exactly eight characters"),
        ("   a    ", "one real character padded to eight"),
        ("short", "under the minimum"),
        ("", "empty"),
        ("12345678", "all digits — the policy rejects these"),
    ],
)
async def test_weak_passwords_are_refused(setup_pending_app, password: str, why: str) -> None:
    """``create_admin`` writes the hash directly, bypassing ``UserManager``."""
    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(
            client, STEP_ADMINISTRATOR, {"email": "root@example.com", "password": password}
        )

    assert resp.status_code == 422, f"accepted a password that is {why}: {resp.text[:120]}"
    # The wizard renders this straight into its error line.
    detail = resp.json().get("detail")
    assert isinstance(detail, str) and detail, f"unusable error body: {resp.text[:200]}"


async def test_malformed_payload_is_422(setup_pending_app) -> None:
    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(client, STEP_ADMINISTRATOR, {"email": "not-an-address"})

    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], str)
