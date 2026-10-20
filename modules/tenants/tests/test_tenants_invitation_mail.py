"""Invitation mail delivery and API feedback."""

import logging

import pytest
from simple_module_core.durable_events import DurableContext, event_key
from simple_module_core.events import EventBus
from simple_module_core.mail import ConsoleMailSender, install_mail_sender
from tenants.contracts.events import InvitationCreated
from tenants.contracts.schemas import InvitationCreate
from tenants.invitations import InvitationService
from tenants.models import Invitation
from tenants.module import TenantsModule
from tenants.service import TenantService


@pytest.fixture
def mail_origin(app, monkeypatch):
    monkeypatch.setattr(app.state.tenants.settings, "public_base_url", "https://app.example.com")


async def _issue(owner):
    await owner.post("/api/tenants/", json={"name": "Acme"})
    return await owner.post(
        "/api/tenants/current/invitations", json={"email": "friend@x.io", "role": "admin"}
    )


async def test_tenants_after_commit_mail(user_client, captured_mail, mail_origin, monkeypatch, app):
    monkeypatch.setattr(app.state.sm.event_bus, "durable_transport", None)
    async with user_client("owner@x.io") as (owner, _):
        response = await _issue(owner)
        assert response.status_code == 201
        assert response.json()["emailed"] is True
        assert len(captured_mail.messages) == 1
        message = captured_mail.messages[0]
        assert message.to == "friend@x.io"
        assert message.subject == "You're invited to join Acme"
        assert response.json()["accept_url"] in message.text
        assert "admin" in message.text


async def test_tenants_relative_mail_skipped(user_client, captured_mail, app, monkeypatch, caplog):
    monkeypatch.setattr(app.state.tenants.settings, "public_base_url", "")
    monkeypatch.setattr(app.state.sm.event_bus, "durable_transport", None)
    with caplog.at_level(logging.WARNING):
        async with user_client("owner@x.io") as (owner, _):
            response = await _issue(owner)
    assert response.status_code == 201
    assert response.json()["emailed"] is False
    assert captured_mail.messages == []
    assert "public_base_url" in caplog.text


async def test_tenants_console_reports_not_emailed(user_client, mail_origin):
    install_mail_sender(ConsoleMailSender(include_body=False))
    async with user_client("owner@x.io") as (owner, _):
        assert (await _issue(owner)).json()["emailed"] is False


async def test_tenants_mail_failure_preserves_invitation(
    user_client, captured_mail, mail_origin, app, monkeypatch, caplog
):
    async def fail(message):
        raise RuntimeError("transport failed")

    monkeypatch.setattr(captured_mail, "send", fail)
    monkeypatch.setattr(app.state.sm.event_bus, "durable_transport", None)
    with caplog.at_level(logging.WARNING):
        async with user_client("owner@x.io") as (owner, _):
            response = await _issue(owner)
            assert response.status_code == 201
            pending = (await owner.get("/api/tenants/current/invitations")).json()
            assert pending[0]["id"] == response.json()["id"]
    assert "Invitation email failed after commit" in caplog.text


async def test_tenants_durable_mail(db_session, captured_mail):
    class Transport:
        def __init__(self):
            self.calls = []

        async def enqueue(self, event, handler_names, db):
            self.calls.append((event, handler_names, db))

    bus = EventBus()
    transport = Transport()
    bus.durable_transport = transport
    TenantsModule().register_event_handlers(bus, None)
    tenants = TenantService(db_session, bus=bus)
    from tenants.contracts.schemas import TenantCreate

    tenant = await tenants.create_tenant(TenantCreate(name="Acme"), owner_user_id="owner")
    invitation, _, url = await InvitationService(tenants, ttl_hours=72).create(
        tenant.id, InvitationCreate(email="friend@x.io"), base_url="https://app.example.com"
    )
    assert await db_session.get(Invitation, invitation.id) is not None
    assert captured_mail.messages == []
    event, names, db = transport.calls[0]
    assert names == ["tenants.send_invitation_email"]
    assert db is db_session
    subscription = bus.durable.lookup(event_key(InvitationCreated), names[0])
    assert subscription is not None
    await subscription.handler(event, DurableContext(db=db_session, attempt=1))
    assert len(captured_mail.messages) == 1
    assert url in captured_mail.messages[0].text


async def test_tenants_durable_relative_link_skipped(db_session, captured_mail, caplog):
    from tenants.invitation_mail import send_invitation_email

    event = InvitationCreated("tenant", "Acme", "friend@x.io", "member", "/accept?token=secret")
    with caplog.at_level(logging.WARNING):
        await send_invitation_email(event, DurableContext(db=db_session, attempt=1))
    assert captured_mail.messages == []
    assert "public_base_url" in caplog.text


async def test_tenants_durable_failure_propagates(db_session, captured_mail, monkeypatch):
    from tenants.invitation_mail import send_invitation_email

    async def fail(message):
        raise RuntimeError("transport failed")

    monkeypatch.setattr(captured_mail, "send", fail)
    event = InvitationCreated(
        "tenant", "Acme", "friend@x.io", "member", "https://app.example.com/accept"
    )
    with pytest.raises(RuntimeError, match="transport failed"):
        await send_invitation_email(event, DurableContext(db=db_session, attempt=1))
