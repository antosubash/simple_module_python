"""Single admin creation/invitation side effects follow the commit (#692, #627)."""

import pytest
from background_tasks.models import OutboxMessage
from simple_module_db import transaction
from sqlalchemy import event
from sqlmodel import select
from test_users_deletion_events import PausedUserTransport, record_user_event
from users.contracts.events import UserCreated, UserInvited
from users.models import User


@pytest.mark.parametrize("operation,event_type", [("invite", UserInvited), ("create", UserCreated)])
@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize("fail_commit", [True, False])
async def test_admin_creation_side_effects_wait_for_commit(
    admin_client, users_app, captured_mail, monkeypatch, operation, event_type, fail_commit, durable
):
    observed = []
    before_commit = []

    async def observe(message):
        observed.append(message)

    bus = users_app.state.sm.event_bus
    bus.subscribe(event_type, observe)
    if durable:
        bus.durable_transport = PausedUserTransport()
        bus.subscribe_durable(event_type, record_user_event)
    email = "commit-boundary@example.com"

    def fail(session):
        raise RuntimeError("forced commit failure")

    finalize = transaction.finalize_session

    async def check_commit(session):
        before_commit.append((list(captured_mail.messages), list(observed)))
        if fail_commit:
            event.listen(session.sync_session, "before_commit", fail, once=True)
        await finalize(session)

    monkeypatch.setattr(transaction, "finalize_session", check_commit)
    db = users_app.state.sm.db
    body = {"email": email, "role_names": []}
    if operation == "create":
        body["password"] = "CompliantPass1!"
    response = await admin_client.post(
        "/api/users/admin/invite" if operation == "invite" else "/api/users/admin", json=body
    )

    assert response.status_code == (500 if fail_commit else 201), response.text
    assert before_commit == [([], [])]
    async with db.session_factory() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        outbox = (await session.execute(select(OutboxMessage))).scalars().all()
    assert len(outbox) == (1 if durable and not fail_commit else 0)
    if fail_commit:
        assert captured_mail.messages == []
        assert observed == []
    else:
        assert user is not None
        assert len(observed) == 1
        assert observed[0].user_id == user.id
        assert observed[0].email == email
        if operation == "invite":
            assert any("/users/invite/accept?token=" in m.text for m in captured_mail.to(email))


async def test_admin_invite_existing_email_is_a_conflict(admin_client, captured_mail):
    body = {"email": "dup-invite@example.com", "role_names": []}
    first = await admin_client.post("/api/users/admin/invite", json=body)
    assert first.status_code == 201, first.text
    sent = len(captured_mail.messages)
    again = await admin_client.post("/api/users/admin/invite", json=body)
    assert again.status_code == 409, again.text
    assert len(captured_mail.messages) == sent
