"""Admin unlock and the locked state in the admin API (GH #530)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from _users_app_builders import ALICE, _client, _login, user_row
from sqlalchemy import select
from users.models import User


async def _lock_by_failing(users_app) -> None:
    for i in range(10):
        r = await _login(users_app, f"10.0.0.{i}", ALICE, "no")
        assert r.status_code == (429 if i == 9 else 400)  # the 10th trips the lock


async def _list_item(admin_client, user_id) -> dict:
    r = await admin_client.get("/api/users/admin", params={"q": "alice"})
    assert r.status_code == 200
    [item] = [u for u in r.json() if u["id"] == str(user_id)]
    return item


async def test_list_reports_locked_until(users_app, admin_client, alice) -> None:
    assert (await _list_item(admin_client, alice.id))["locked_until"] is None
    await _lock_by_failing(users_app)
    assert (await _list_item(admin_client, alice.id))["locked_until"] is not None


async def test_expired_lock_is_not_reported(users_app, admin_client, alice) -> None:
    async with users_app.state.sm.db.session_factory() as session:
        row = await session.get(User, alice.id)
        assert row is not None
        row.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (await _list_item(admin_client, alice.id))["locked_until"] is None


async def test_unlock_clears_lock_and_is_audited(users_app, admin_client, alice) -> None:
    from audit_log.models import AuditEntry

    await _lock_by_failing(users_app)
    r = await admin_client.patch(f"/api/users/admin/{alice.id}/unlock")
    assert r.status_code == 200
    assert r.json()["locked_until"] is None

    row = await user_row(users_app, ALICE)
    assert (row.locked_until, row.failed_login_count, row.last_failed_login_at) == (None, 0, None)

    async with users_app.state.sm.db.session_factory() as session:
        stmt = select(AuditEntry).where(
            AuditEntry.entity_type == "User", AuditEntry.entity_id == str(alice.id)
        )
        entries = [e for e in (await session.execute(stmt)).scalars() if e.action == "updated"]
    fields = [sorted(c["field"] for c in e.changes) for e in entries]
    # One entry for the lock, one for the unlock, nothing for the nine plain failures.
    assert [f for f in fields if "locked_until" in f] == [["locked_until"], ["locked_until"]]
    assert all("failed_login_count" not in f for f in fields)
    assert len(entries) == 2

    # The account signs in again.
    login = await _login(users_app, "9.9.9.9", ALICE, "UserPass1!")
    assert login.status_code == 204


async def test_unlock_unknown_user_is_404(admin_client) -> None:
    r = await admin_client.patch("/api/users/admin/00000000-0000-0000-0000-000000000000/unlock")
    assert r.status_code == 404


async def test_unlock_requires_manage(user_client, alice) -> None:
    r = await user_client.patch(f"/api/users/admin/{alice.id}/unlock")
    assert r.status_code == 403


async def test_password_reset_lifts_the_lock(users_app, admin_client, alice) -> None:
    """Proving control of the mailbox is the way out of a lockout."""
    from audit_log.models import AuditEntry

    await _lock_by_failing(users_app)
    assert (await _login(users_app, "9.9.9.9", ALICE, "UserPass1!")).status_code == 429
    link = await admin_client.post(f"/api/users/admin/{alice.id}/reset-password-link")
    token = link.json()["link"].split("token=", 1)[1]
    async with _client(users_app, "7.7.7.7") as c:
        reset = await c.post(
            "/api/users/auth/reset-password", json={"token": token, "password": "NewPass1!x"}
        )
    assert reset.status_code == 200, reset.text

    row = await user_row(users_app, ALICE)
    assert (row.locked_until, row.failed_login_count, row.last_failed_login_at) == (None, 0, None)
    assert (await _login(users_app, "9.9.9.9", ALICE, "NewPass1!x")).status_code == 204

    async with users_app.state.sm.db.session_factory() as session:
        stmt = select(AuditEntry).where(
            AuditEntry.entity_id == str(alice.id), AuditEntry.action == "updated"
        )
        changes = [c for e in (await session.execute(stmt)).scalars() for c in e.changes]
    assert [c["field"] for c in changes].count("locked_until") == 2  # the lock and the unlock
