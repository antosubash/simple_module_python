"""Render and deliver invitation mail."""

from __future__ import annotations

import logging
from functools import cache
from importlib.resources import files
from string import Template
from urllib.parse import urlsplit

from simple_module_core.durable_events import DurableContext
from simple_module_core.mail import (
    MailMessage,
    current_mail_sender,
    mail_transport_installed,
    resolve_mail_sender,
)

from tenants import constants as c
from tenants.contracts.events import InvitationCreated

logger = logging.getLogger(__name__)


def absolute_accept_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme in c.MAIL_URL_SCHEMES and bool(parsed.netloc)


def invitation_mail_wanted(url: str) -> bool:
    """Whether to queue an invitation email at all (see ``InvitationService.create``)."""
    # A sender that only logs (console backend) gets nothing either: the UI
    # already hands the link back, and queuing would store the token for nothing.
    if not mail_transport_installed() or not current_mail_sender().delivers_email:
        return False
    if not absolute_accept_url(url):
        logger.warning(c.MAIL_RELATIVE_WARNING)
        return False
    return True


def invitation_emailed(url: str) -> bool:
    return current_mail_sender().delivers_email and absolute_accept_url(url)


@cache
def _template() -> Template:
    return Template(files(c.MODULE_PACKAGE).joinpath(c.INVITATION_TEMPLATE).read_text())


def invitation_message(event: InvitationCreated) -> MailMessage:
    return MailMessage(
        to=event.email,
        subject=c.INVITATION_MAIL_SUBJECT.format(tenant_name=event.tenant_name),
        text=_template().substitute(
            tenant_name=event.tenant_name, role=event.role, accept_url=event.accept_url
        ),
    )


async def send_invitation_email(event: InvitationCreated, ctx: DurableContext) -> None:
    """Propagate failures for outbox retries; never commit the worker session."""
    if not absolute_accept_url(event.accept_url):
        logger.warning(c.MAIL_RELATIVE_WARNING)
        return
    if not mail_transport_installed():
        # The web process had a transport when it queued this; a worker started
        # without the mail module must not mark it delivered. Fail and retry.
        raise RuntimeError(c.MAIL_NO_TRANSPORT_ERROR)
    sender = await resolve_mail_sender(ctx.db)
    await sender.send(invitation_message(event))


async def send_invitation_after_commit(event: InvitationCreated) -> None:
    try:
        await send_invitation_email(event, DurableContext(db=None, attempt=1))
    except Exception:
        logger.warning(c.MAIL_FAILURE_WARNING, exc_info=True)
